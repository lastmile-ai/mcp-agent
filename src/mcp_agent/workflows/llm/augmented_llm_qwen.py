import json
import re
from typing import Iterable, List, Optional, Type, Union, Dict, Any
from datetime import datetime

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from mcp.types import (
    CallToolRequestParams,
    CallToolRequest,
    ModelPreferences,
)

from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    ModelT,
    RequestParams,
)
from mcp_agent.workflows.llm.augmented_llm_openai import (
    MCPOpenAITypeConverter,
    mcp_content_to_openai_content,
    openai_content_to_mcp_content,
)
from mcp_agent.logging.logger import get_logger


class QwenAugmentedLLM(AugmentedLLM[ChatCompletionMessageParam, ChatCompletionMessage]):
    """
    An implementation of AugmentedLLM that uses Qwen2.5 models through Ollama's
    OpenAI-compatible API interface, with support for Qwen's specific function
    calling template format.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, type_converter=MCPOpenAITypeConverter, **kwargs)

        self.provider = "Qwen"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )

        # Get default model from config if available
        chosen_model = "qwen2.5-coder-32b-instruct"  # Fallback default

        if self.context and self.context.config and self.context.config.qwen:
            if hasattr(self.context.config.qwen, "default_model"):
                chosen_model = self.context.config.qwen.default_model

        self.default_request_params = self.default_request_params or RequestParams(
            model=chosen_model,
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

    def _format_qwen_system_message(
        self, instruction: str, tools: List[Dict[str, Any]]
    ) -> str:
        """Format a system message with tools in Qwen2.5's expected format."""
        current_date = datetime.now().strftime("%Y-%m-%d")

        system_message = f"""You are Qwen, created by Alibaba Cloud. You are a helpful assistant.

Current Date: {current_date}

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
"""

        # Add tool definitions
        for tool in tools:
            system_message += json.dumps(tool) + "\n"

        system_message += """</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>

"""

        # Add any additional instructions
        if instruction:
            system_message += f"\n{instruction}"

        return system_message

    def _process_tool_response(self, tool_call_id: str, content: str) -> str:
        """Format a tool response in Qwen2.5's expected format."""
        return f"<tool_response>\n{content}\n</tool_response>"

    async def generate(self, message, request_params: RequestParams | None = None):
        """
        Process a query using an LLM and available tools.
        This implementation uses Qwen2.5 with Ollama's OpenAI-compatible API.
        """
        config = self.context.config
        openai_client = OpenAI(
            api_key=config.qwen.api_key, base_url=config.qwen.base_url
        )
        messages: List[ChatCompletionMessageParam] = []
        params = self.get_request_params(request_params)

        # Get available tools
        response = await self.aggregator.list_tools()
        available_tools: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in response.tools
        ]

        # Format system message with Qwen-specific template
        system_prompt = self._format_qwen_system_message(
            self.instruction or params.systemPrompt, available_tools
        )

        if len(messages) == 0:
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=system_prompt)
            )

        # Add history if requested
        if params.use_history:
            history = self.history.get()
            # Skip the initial system message from history if we just added one
            if (
                history
                and isinstance(history[0], dict)
                and history[0].get("role") == "system"
                and len(messages) > 0
                and isinstance(messages[0], dict)
                and messages[0].get("role") == "system"
            ):
                history = history[1:]
            messages.extend(history)

        # Add the current message
        if isinstance(message, str):
            messages.append(
                ChatCompletionUserMessageParam(role="user", content=message)
            )
        elif isinstance(message, list):
            messages.extend(message)
        else:
            messages.append(message)

        responses: List[ChatCompletionMessage] = []
        model = await self.select_model(params)

        for i in range(params.max_iterations):
            arguments = {
                "model": model,
                "messages": messages,
                "max_tokens": params.maxTokens,
                "stop": params.stopSequences,
            }

            if params.metadata:
                arguments = {**arguments, **params.metadata}

            self.logger.debug(f"{arguments}")
            self._log_chat_progress(chat_turn=len(messages) // 2, model=model)

            executor_result = await self.executor.execute(
                openai_client.chat.completions.create, **arguments
            )

            response = executor_result[0]

            self.logger.debug(
                "Qwen ChatCompletion response:",
                data=response,
            )

            if isinstance(response, BaseException):
                self.logger.error(f"Error: {response}")
                break

            if not response.choices or len(response.choices) == 0:
                # No response from the model, we're done
                break

            choice = response.choices[0]
            message = choice.message
            responses.append(message)

            # Extract tool calls from the content using regex
            content = message.content or ""
            tool_calls_matches = re.findall(
                r"<tool_call>(.*?)</tool_call>", content, re.DOTALL
            )

            tool_tasks = []

            for tool_call_match in tool_calls_matches:
                try:
                    tool_call_data = json.loads(tool_call_match.strip())
                    tool_name = tool_call_data.get("name")
                    tool_args = tool_call_data.get("arguments", {})

                    if not tool_name:
                        continue

                    tool_call_id = f"call_{len(tool_tasks)}"

                    tool_call_request = CallToolRequest(
                        method="tools/call",
                        params=CallToolRequestParams(
                            name=tool_name, arguments=tool_args
                        ),
                    )

                    # Add the task
                    tool_tasks.append(
                        self.call_tool(
                            request=tool_call_request, tool_call_id=tool_call_id
                        )
                    )

                except json.JSONDecodeError:
                    self.logger.error(f"Failed to parse tool call: {tool_call_match}")
                    continue

            if tool_tasks:
                # Execute all tools in parallel
                tool_results = await self.executor.execute(*tool_tasks)
                self.logger.debug(
                    f"Iteration {i}: Tool call results: {str(tool_results) if tool_results else 'None'}"
                )

                # Create user message with tool responses
                tool_responses = []
                for idx, result in enumerate(tool_results):
                    if isinstance(result, BaseException):
                        self.logger.error(
                            f"Warning: Unexpected error during tool execution: {result}. Continuing..."
                        )
                        continue

                    if result.content:
                        tool_id = f"call_{idx}"
                        content_str = "\n".join(
                            json.dumps(content.__dict__, default=str)
                            for content in result.content
                        )
                        tool_responses.append(
                            self._process_tool_response(tool_id, content_str)
                        )

                if tool_responses:
                    tool_response_message = ChatCompletionUserMessageParam(
                        role="user", content="\n".join(tool_responses)
                    )
                    messages.append(tool_response_message)
            else:
                # No tool calls, we're done with this iteration
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
        Process a query using Qwen2.5 and return the result as a string.
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

            # Remove any tool_call XML tags from the response
            cleaned_content = re.sub(
                r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL
            )

            if cleaned_content.strip():
                final_text.append(cleaned_content.strip())

        return "\n".join(final_text)

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """
        Generate a structured response using Instructor with Qwen2.5.
        """
        import instructor

        response = await self.generate_str(
            message=message,
            request_params=request_params,
        )

        client = instructor.from_openai(
            OpenAI(
                api_key=self.context.config.qwen.api_key,
                base_url=self.context.config.qwen.base_url,
            ),
            mode=instructor.Mode.TOOLS,
        )

        params = self.get_request_params(request_params)
        model = await self.select_model(params)

        structured_response = client.chat.completions.create(
            model=model,
            response_model=response_model,
            messages=[
                {"role": "user", "content": response},
            ],
        )

        return structured_response
