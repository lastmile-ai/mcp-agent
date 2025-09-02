from typing import Type

from openai import AsyncOpenAI

from mcp_agent.executor.workflow_task import workflow_task
from mcp_agent.utils.pydantic_type_serializer import serialize_model, deserialize_model
from mcp_agent.workflows.llm.augmented_llm import (
    ModelT,
    RequestParams,
)
from mcp_agent.workflows.llm.augmented_llm_openai import (
    OpenAIAugmentedLLM,
    RequestStructuredCompletionRequest,
)


class OllamaAugmentedLLM(OpenAIAugmentedLLM):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    This implementation uses Ollama's OpenAI-compatible ChatCompletion API.
    """

    def __init__(self, *args, **kwargs):
        # Create a copy of kwargs to avoid modifying the original
        updated_kwargs = kwargs.copy()

        # Only set default_model if it's not already in kwargs
        if "default_model" not in updated_kwargs:
            updated_kwargs["default_model"] = "llama3.2:3b"

        super().__init__(*args, **updated_kwargs)

        self.provider = "Ollama"

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        # First we invoke the LLM to generate a string response
        # We need to do this in a two-step process because Instructor doesn't
        # know how to invoke MCP tools via call_tool, so we'll handle all the
        # processing first and then pass the final response through Instructor

        response = await self.generate_str(
            message=message,
            request_params=request_params,
        )

        params = self.get_request_params(request_params)
        model = await self.select_model(params) or "llama3.2:3b"

        serialized_response_model: str | None = None

        if self.executor and self.executor.execution_engine == "temporal":
            # Serialize the response model to a string
            serialized_response_model = serialize_model(response_model)

        structured_response = await self.executor.execute(
            OllamaCompletionTasks.request_structured_completion_task,
            RequestStructuredCompletionRequest(
                config=self.context.config.openai,
                response_model=response_model
                if not serialized_response_model
                else None,
                serialized_response_model=serialized_response_model,
                response_str=response,
                model=model,
            ),
        )

        # TODO: saqadri (MAC) - fix request_structured_completion_task to return ensure_serializable
        # Convert dict back to the proper model instance if needed
        if isinstance(structured_response, dict):
            structured_response = response_model.model_validate(structured_response)

        return structured_response


class OllamaCompletionTasks:
    @staticmethod
    @workflow_task
    async def request_structured_completion_task(
        request: RequestStructuredCompletionRequest,
    ) -> ModelT:
        """
        Request a structured completion using Instructor's OpenAI API.
        """
        import instructor

        if request.response_model:
            response_model = request.response_model
        elif request.serialized_response_model:
            response_model = deserialize_model(request.serialized_response_model)
        else:
            raise ValueError(
                "Either response_model or serialized_response_model must be provided for structured completion."
            )

        # Next we pass the text through instructor to extract structured data
        async with AsyncOpenAI(
            api_key=request.config.api_key,
            base_url=request.config.base_url,
            http_client=request.config.http_client
            if hasattr(request.config, "http_client")
            else None,
        ) as async_client:
            client = instructor.from_openai(
                async_client,
                mode=instructor.Mode.JSON,
            )

            # Extract structured data from natural language
            structured_response = await client.chat.completions.create(
                model=request.model,
                response_model=response_model,
                messages=[
                    {"role": "user", "content": request.response_str},
                ],
            )

            return structured_response
