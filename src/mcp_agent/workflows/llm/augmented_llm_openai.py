import json
import re
import functools
from typing import Any, Iterable, List, Type

from pydantic import BaseModel

from openai import OpenAI, AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartRefusalParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletion,
)
from mcp.types import (
    CallToolRequestParams,
    CallToolRequest,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ListToolsResult,
    ModelPreferences,
    TextContent,
    TextResourceContents,
)

from mcp_agent.config import OpenAISettings
from mcp_agent.executor.workflow_task import workflow_task
from mcp_agent.utils.common import ensure_serializable, typed_dict_extras
from mcp_agent.utils.pydantic_type_serializer import serialize_model, deserialize_model
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    ModelT,
    MCPMessageParam,
    MCPMessageResult,
    ProviderToMCPConverter,
    RequestParams,
)
from mcp_agent.logging.logger import get_logger


class OpenAIAugmentedLLM(
    AugmentedLLM[ChatCompletionMessageParam, ChatCompletionMessage]
):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    This implementation uses OpenAI's ChatCompletion as the LLM.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, type_converter=MCPOpenAITypeConverter, **kwargs)

        self.provider = "OpenAI"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )

        # Get default model from config if available
        if "default_model" in kwargs:
            default_model = kwargs["default_model"]
        else:
            default_model = "gpt-4o"  # Fallback default

        self._reasoning_effort = "medium"
        if self.context and self.context.config and self.context.config.openai:
            if hasattr(self.context.config.openai, "default_model"):
                default_model = self.context.config.openai.default_model
            if hasattr(self.context.config.openai, "reasoning_effort"):
                self._reasoning_effort = self.context.config.openai.reasoning_effort

        self._reasoning = lambda model: model.startswith(("o1", "o3", "o4"))

        if self._reasoning(default_model):
            self.logger.info(
                f"Using reasoning model '{default_model}' with '{self._reasoning_effort}' reasoning effort"
            )

        self.default_request_params = self.default_request_params or RequestParams(
            model=default_model,
            modelPreferences=self.model_preferences,
            maxTokens=4096,
            systemPrompt=self.instruction,
            parallel_tool_calls=False,
            max_iterations=10,
            use_history=True,
        )

    @classmethod
    def convert_message_to_message_param(
        cls, message: ChatCompletionMessage, **kwargs
    ) -> ChatCompletionMessageParam:
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        assistant_message_params = {
            "role": "assistant",
            "audio": message.audio,
            "refusal": message.refusal,
            **kwargs,
        }
        if message.content is not None:
            assistant_message_params["content"] = message.content
        if message.tool_calls is not None:
            assistant_message_params["tool_calls"] = message.tool_calls

        return ChatCompletionAssistantMessageParam(**assistant_message_params)

    async def generate(self, message, request_params: RequestParams | None = None):
        """
        Process a query using an LLM and available tools.
        The default implementation uses OpenAI's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """
        messages: List[ChatCompletionMessageParam] = []
        params = self.get_request_params(request_params)

        if params.use_history:
            messages.extend(self.history.get())

        system_prompt = self.instruction or params.systemPrompt
        if system_prompt and len(messages) == 0:
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=system_prompt)
            )

        if isinstance(message, str):
            messages.append(
                ChatCompletionUserMessageParam(role="user", content=message)
            )
        elif isinstance(message, list):
            messages.extend(message)
        else:
            messages.append(message)

        response: ListToolsResult = await self.agent.list_tools()
        available_tools: List[ChatCompletionToolParam] = [
            ChatCompletionToolParam(
                type="function",
                function={
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                    # TODO: saqadri - determine if we should specify "strict" to True by default
                },
            )
            for tool in response.tools
        ]
        if not available_tools:
            available_tools = None

        responses: List[ChatCompletionMessage] = []
        model = await self.select_model(params)

        for i in range(params.max_iterations):
            arguments = {
                "model": model,
                "messages": messages,
                "stop": params.stopSequences,
                "tools": available_tools,
            }
            if self._reasoning(model):
                arguments = {
                    **arguments,
                    # DEPRECATED: https://platform.openai.com/docs/api-reference/chat/create#chat-create-max_tokens
                    # "max_tokens": params.maxTokens,
                    "max_completion_tokens": params.maxTokens,
                    "reasoning_effort": self._reasoning_effort,
                }
            else:
                arguments = {**arguments, "max_tokens": params.maxTokens}
                # if available_tools:
                #     arguments["parallel_tool_calls"] = params.parallel_tool_calls

            if params.metadata:
                arguments = {**arguments, **params.metadata}

            self.logger.debug(f"{arguments}")
            self._log_chat_progress(chat_turn=len(messages) // 2, model=model)

            request = ensure_serializable(
                RequestCompletionRequest(
                    config=self.context.config.openai,
                    payload=arguments,
                ),
            )
            response: ChatCompletion = await self.executor.execute(
                OpenAICompletionTasks.request_completion_task, request
            )

            self.logger.debug(
                "OpenAI ChatCompletion response:",
                data=response,
            )

            if isinstance(response, BaseException):
                self.logger.error(f"Error: {response}")
                break

            if not response.choices or len(response.choices) == 0:
                # No response from the model, we're done
                break

            # TODO: saqadri - handle multiple choices for more complex interactions.
            # Keeping it simple for now because multiple choices will also complicate memory management
            choice = response.choices[0]
            message = choice.message
            responses.append(message)

            # Fixes an issue with openai validation that does not allow non alphanumeric characters, dashes, and underscores
            sanitized_name = (
                re.sub(r"[^a-zA-Z0-9_-]", "_", self.name)
                if isinstance(self.name, str)
                else None
            )

            converted_message = self.convert_message_to_message_param(
                message, name=sanitized_name
            )
            messages.append(converted_message)

            if (
                choice.finish_reason in ["tool_calls", "function_call"]
                and message.tool_calls
            ):
                # Execute all tool calls in parallel using functools.partial to bind arguments
                tool_tasks = [
                    functools.partial(self.execute_tool_call, tool_call=tool_call)
                    for tool_call in message.tool_calls
                ]
                # Wait for all tool calls to complete.
                tool_results = await self.executor.execute_many(tool_tasks)
                self.logger.debug(
                    f"Iteration {i}: Tool call results: {str(tool_results) if tool_results else 'None'}"
                )
                # Add non-None results to messages.
                for result in tool_results:
                    if isinstance(result, BaseException):
                        self.logger.error(
                            f"Warning: Unexpected error during tool execution: {result}. Continuing..."
                        )
                        continue
                    if result is not None:
                        messages.append(result)
            elif choice.finish_reason == "length":
                # We have reached the max tokens limit
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'length'"
                )
                # TODO: saqadri - would be useful to return the reason for stopping to the caller
                break
            elif choice.finish_reason == "content_filter":
                # The response was filtered by the content filter
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'content_filter'"
                )
                # TODO: saqadri - would be useful to return the reason for stopping to the caller
                break
            elif choice.finish_reason == "stop":
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'stop'"
                )
                break

        if params.use_history:
            self.history.set(messages)

        self._log_chat_finished(model=model)

        return responses

    async def generate_str(
        self,
        message,
        request_params: RequestParams | None = None,
    ):
        """
        Process a query using an LLM and available tools.
        The default implementation uses OpenAI's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """
        responses = await self.generate(
            message=message,
            request_params=request_params,
        )

        final_text: List[str] = []

        for response in responses:
            content = response.content
            if not content:
                continue

            if isinstance(content, str):
                final_text.append(content)
                continue

        return "\n".join(final_text)

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
        model = await self.select_model(params) or "gpt-4o"

        serialized_response_model: str | None = None

        if self.executor and self.executor.execution_engine == "temporal":
            # Serialize the response model to a string
            serialized_response_model = serialize_model(response_model)

        structured_response = await self.executor.execute(
            OpenAICompletionTasks.request_structured_completion_task,
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

    async def pre_tool_call(self, tool_call_id: str | None, request: CallToolRequest):
        return request

    async def post_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest, result: CallToolResult
    ):
        return result

    async def execute_tool_call(
        self,
        tool_call: ChatCompletionMessageToolCall,
    ) -> ChatCompletionToolMessageParam | None:
        """
        Execute a single tool call and return the result message.
        Returns None if there's no content to add to messages.
        """
        tool_name = tool_call.function.name
        tool_args_str = tool_call.function.arguments
        tool_call_id = tool_call.id
        tool_args = {}

        try:
            if tool_args_str:
                tool_args = json.loads(tool_args_str)
        except json.JSONDecodeError as e:
            return ChatCompletionToolMessageParam(
                role="tool",
                tool_call_id=tool_call_id,
                content=f"Invalid JSON provided in tool call arguments for '{tool_name}'. Failed to load JSON: {str(e)}",
            )

        tool_call_request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=tool_name, arguments=tool_args),
        )

        result = await self.call_tool(
            request=tool_call_request, tool_call_id=tool_call_id
        )

        if result.content:
            return ChatCompletionToolMessageParam(
                role="tool",
                tool_call_id=tool_call_id,
                content="\n".join(
                    str(mcp_content_to_openai_content_part(c)) for c in result.content
                ),
            )

        return None

    def message_param_str(self, message: ChatCompletionMessageParam) -> str:
        """Convert an input message to a string representation."""
        if message.get("content"):
            content = message["content"]
            if isinstance(content, str):
                return content
            else:  # content is a list
                final_text: List[str] = []
                for part in content:
                    text_part = part.get("text")
                    if text_part:
                        final_text.append(str(text_part))
                    else:
                        final_text.append(str(part))

                return "\n".join(final_text)

        return str(message)

    def message_str(self, message: ChatCompletionMessage) -> str:
        """Convert an output message to a string representation."""
        content = message.content
        if content:
            return content

        return str(message)


class RequestCompletionRequest(BaseModel):
    config: OpenAISettings
    payload: dict


class RequestStructuredCompletionRequest(BaseModel):
    config: OpenAISettings
    response_model: Any | None = None
    serialized_response_model: str | None = None
    response_str: str
    model: str


class OpenAICompletionTasks:
    @staticmethod
    @workflow_task
    async def request_completion_task(
        request: RequestCompletionRequest,
    ) -> ChatCompletion:
        """
        Request a completion from OpenAI's API.
        """

        openai_client = OpenAI(
            api_key=request.config.api_key,
            base_url=request.config.base_url,
            http_client=request.config.http_client
            if hasattr(request.config, "http_client")
            else None,
        )

        payload = request.payload
        response = openai_client.chat.completions.create(**payload)
        response = ensure_serializable(response)
        return response

    @staticmethod
    @workflow_task
    async def request_structured_completion_task(
        request: RequestStructuredCompletionRequest,
    ) -> ModelT:
        """
        Request a structured completion using Instructor's OpenAI API.
        """
        import instructor
        from instructor.exceptions import InstructorRetryException

        if request.response_model:
            response_model = request.response_model
        elif request.serialized_response_model:
            response_model = deserialize_model(request.serialized_response_model)
        else:
            raise ValueError(
                "Either response_model or serialized_response_model must be provided for structured completion."
            )

        # Next we pass the text through instructor to extract structured data
        client = instructor.from_openai(
            AsyncOpenAI(
                api_key=request.config.api_key,
                base_url=request.config.base_url,
                http_client=request.config.http_client
                if hasattr(request.config, "http_client")
                else None,
            ),
            mode=instructor.Mode.TOOLS_STRICT,
        )

        try:
            # Extract structured data from natural language
            structured_response = await client.chat.completions.create(
                model=request.model,
                response_model=response_model,
                messages=[
                    {"role": "user", "content": request.response_str},
                ],
            )
        except InstructorRetryException:
            # Retry the request with JSON mode
            client = instructor.from_openai(
                AsyncOpenAI(
                    api_key=request.config.api_key,
                    base_url=request.config.base_url,
                    http_client=request.config.http_client
                    if hasattr(request.config, "http_client")
                    else None,
                ),
                mode=instructor.Mode.JSON,
            )

            structured_response = await client.chat.completions.create(
                model=request.model,
                response_model=response_model,
                messages=[
                    {"role": "user", "content": request.response_str},
                ],
            )

        return structured_response


class MCPOpenAITypeConverter(
    ProviderToMCPConverter[ChatCompletionMessageParam, ChatCompletionMessage]
):
    """
    Convert between OpenAI and MCP types.
    """

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> ChatCompletionMessage:
        # MCPMessageResult -> ChatCompletionMessage
        if result.role != "assistant":
            raise ValueError(
                f"Expected role to be 'assistant' but got '{result.role}' instead."
            )

        return ChatCompletionMessage(
            role="assistant",
            content=result.content.text or str(result.context),
            # Lossy conversion for the following fields:
            # result.model
            # result.stopReason
        )

    @classmethod
    def to_mcp_message_result(cls, result: ChatCompletionMessage) -> MCPMessageResult:
        # ChatCompletionMessage -> MCPMessageResult
        return MCPMessageResult(
            role=result.role,
            content=TextContent(type="text", text=result.content),
            model="",
            stopReason=None,
            # extras for ChatCompletionMessage fields
            **result.model_dump(exclude={"role", "content"}),
        )

    @classmethod
    def from_mcp_message_param(
        cls, param: MCPMessageParam
    ) -> ChatCompletionMessageParam:
        # MCPMessageParam -> ChatCompletionMessageParam
        if param.role == "assistant":
            extras = param.model_dump(exclude={"role", "content"})
            return ChatCompletionAssistantMessageParam(
                role="assistant",
                content=[mcp_content_to_openai_content_part(param.content)],
                **extras,
            )
        elif param.role == "user":
            extras = param.model_dump(exclude={"role", "content"})
            return ChatCompletionUserMessageParam(
                role="user",
                content=[mcp_content_to_openai_content_part(param.content)],
                **extras,
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, MCP only supports 'assistant' and 'user'"
            )

    @classmethod
    def to_mcp_message_param(cls, param: ChatCompletionMessageParam) -> MCPMessageParam:
        # ChatCompletionMessage -> MCPMessageParam

        contents = openai_content_to_mcp_content(param.content)

        # TODO: saqadri - the mcp_content can have multiple elements
        # while sampling message content has a single content element
        # Right now we error out if there are > 1 elements in mcp_content
        # We need to handle this case properly going forward
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported"
            )
        mcp_content: TextContent | ImageContent | EmbeddedResource = contents[0]

        if param.role == "assistant":
            return MCPMessageParam(
                role="assistant",
                content=mcp_content,
                **typed_dict_extras(param, ["role", "content"]),
            )
        elif param.role == "user":
            return MCPMessageParam(
                role="user",
                content=mcp_content,
                **typed_dict_extras(param, ["role", "content"]),
            )
        elif param.role == "tool":
            raise NotImplementedError(
                "Tool messages are not supported in SamplingMessage yet"
            )
        elif param.role == "system":
            raise NotImplementedError(
                "System messages are not supported in SamplingMessage yet"
            )
        elif param.role == "developer":
            raise NotImplementedError(
                "Developer messages are not supported in SamplingMessage yet"
            )
        elif param.role == "function":
            raise NotImplementedError(
                "Function messages are not supported in SamplingMessage yet"
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, MCP only supports 'assistant', 'user', 'tool', 'system', 'developer', and 'function'"
            )


def mcp_content_to_openai_content_part(
    content: TextContent | ImageContent | EmbeddedResource,
) -> ChatCompletionContentPartParam:
    if isinstance(content, TextContent):
        return ChatCompletionContentPartTextParam(type="text", text=content.text)
    elif isinstance(content, ImageContent):
        # Best effort to convert an image to text
        return ChatCompletionContentPartTextParam(
            type="text", text=f"{content.mimeType}:{content.data}"
        )
    elif isinstance(content, EmbeddedResource):
        if isinstance(content.resource, TextResourceContents):
            return ChatCompletionContentPartTextParam(
                type="text", text=content.resource.text
            )
        else:  # BlobResourceContents
            return ChatCompletionContentPartTextParam(
                type="text", text=f"{content.resource.mimeType}:{content.resource.blob}"
            )
    else:
        # Last effort to convert the content to a string
        return ChatCompletionContentPartTextParam(type="text", text=str(content))


def openai_content_to_mcp_content(
    content: str
    | Iterable[ChatCompletionContentPartParam | ChatCompletionContentPartRefusalParam],
) -> Iterable[TextContent | ImageContent | EmbeddedResource]:
    mcp_content = []

    if isinstance(content, str):
        mcp_content = [TextContent(type="text", text=content)]
    else:
        # TODO: saqadri - this is a best effort conversion, we should handle all possible content types
        for c in content:
            if c.type == "text":  # isinstance(c, ChatCompletionContentPartTextParam):
                mcp_content.append(
                    TextContent(
                        type="text", text=c.text, **typed_dict_extras(c, ["text"])
                    )
                )
            elif (
                c.type == "image_url"
            ):  # isinstance(c, ChatCompletionContentPartImageParam):
                raise NotImplementedError("Image content conversion not implemented")
                # TODO: saqadri - need to download the image into a base64-encoded string
                # Download image from c.image_url
                # return ImageContent(
                #     type="image",
                #     data=downloaded_image,
                #     **c
                # )
            elif (
                c.type == "input_audio"
            ):  # isinstance(c, ChatCompletionContentPartInputAudioParam):
                raise NotImplementedError("Audio content conversion not implemented")
            elif (
                c.type == "refusal"
            ):  # isinstance(c, ChatCompletionContentPartRefusalParam):
                mcp_content.append(
                    TextContent(
                        type="text", text=c.refusal, **typed_dict_extras(c, ["refusal"])
                    )
                )
            else:
                raise ValueError(f"Unexpected content type: {c.type}")

    return mcp_content
