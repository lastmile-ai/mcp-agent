import json
import re
import functools
from typing import Any, Dict, Iterable, List, Type, cast

from pydantic import BaseModel


from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
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
from opentelemetry import trace
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
from mcp_agent.tracing.telemetry import get_tracer, telemetry
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.tracing.semconv import (
    GEN_AI_AGENT_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_NAME,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)
from mcp_agent.tracing.telemetry import is_otel_serializable
from mcp_agent.utils.common import ensure_serializable, typed_dict_extras
from mcp_agent.utils.mime_utils import image_url_to_mime_and_base64
from mcp_agent.utils.pydantic_type_serializer import deserialize_model
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageTypes,
    ModelT,
    MCPMessageParam,
    MCPMessageResult,
    ProviderToMCPConverter,
    RequestParams,
)
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.multipart_converter_openai import OpenAIConverter


class RequestCompletionRequest(BaseModel):
    config: OpenAISettings
    payload: dict


class RequestStructuredCompletionRequest(BaseModel):
    config: OpenAISettings
    response_model: Any | None = None
    serialized_response_model: str | None = None
    response_str: str
    model: str
    user: str | None = None
    strict: bool = False


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

        self._reasoning = lambda model: model and model.startswith(
            ("o1", "o3", "o4", "gpt-5")
        )

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

    @track_tokens()
    async def generate(
        self,
        message,
        request_params: RequestParams | None = None,
    ):
        """
        Process a query using an LLM and available tools.
        The default implementation uses OpenAI's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            self._annotate_span_for_generation_message(span, message)

            messages: List[ChatCompletionMessageParam] = []
            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            if params.use_history:
                messages.extend(self.history.get())

            system_prompt = self.instruction or params.systemPrompt
            if system_prompt and len(messages) == 0:
                span.set_attribute("system_prompt", system_prompt)
                messages.append(
                    ChatCompletionSystemMessageParam(
                        role="system", content=system_prompt
                    )
                )
            messages.extend((OpenAIConverter.convert_mixed_messages_to_openai(message)))

            response: ListToolsResult = await self.agent.list_tools(
                tool_filter=params.tool_filter
            )
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

            if self.context.tracing_enabled:
                span.set_attribute(
                    "available_tools",
                    [t.get("function", {}).get("name") for t in available_tools],
                )
            if not available_tools:
                available_tools = None

            responses: List[ChatCompletionMessage] = []
            model = await self.select_model(params)
            if model:
                span.set_attribute(GEN_AI_REQUEST_MODEL, model)

            # prefer user from the request params,
            # otherwise use the default from the config
            user = params.user or getattr(self.context.config.openai, "user", None)
            if self.context.tracing_enabled and user:
                span.set_attribute("user", user)

            total_input_tokens = 0
            total_output_tokens = 0
            finish_reasons = []

            for i in range(params.max_iterations):
                arguments = {
                    "model": model,
                    "messages": messages,
                    "tools": available_tools,
                }

                if user:
                    arguments["user"] = user

                if params.stopSequences is not None:
                    arguments["stop"] = params.stopSequences

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

                self.logger.debug("Completion request arguments:", data=arguments)
                self._log_chat_progress(chat_turn=len(messages) // 2, model=model)

                request = RequestCompletionRequest(
                    config=self.context.config.openai,
                    payload=arguments,
                )

                self._annotate_span_for_completion_request(span, request, i)

                response: ChatCompletion = await self.executor.execute(
                    OpenAICompletionTasks.request_completion_task,
                    ensure_serializable(request),
                )

                self.logger.debug(
                    "OpenAI ChatCompletion response:",
                    data=response,
                )

                if isinstance(response, BaseException):
                    self.logger.error(f"Error: {response}")
                    span.record_exception(response)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    break

                self._annotate_span_for_completion_response(span, response, i)

                # Per-iteration token counts
                iteration_input = response.usage.prompt_tokens
                iteration_output = response.usage.completion_tokens

                total_input_tokens += iteration_input
                total_output_tokens += iteration_output

                # Incremental token tracking inside loop so watchers update during long runs
                if self.context.token_counter:
                    await self.context.token_counter.record_usage(
                        input_tokens=iteration_input,
                        output_tokens=iteration_output,
                        model_name=model,
                        provider=self.provider,
                    )

                if not response.choices or len(response.choices) == 0:
                    # No response from the model, we're done
                    break

                # TODO: saqadri - handle multiple choices for more complex interactions.
                # Keeping it simple for now because multiple choices will also complicate memory management
                choice = response.choices[0]
                message = choice.message
                responses.append(message)
                finish_reasons.append(choice.finish_reason)

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
                            span.record_exception(result)
                            continue
                        if result is not None:
                            messages.append(result)
                elif choice.finish_reason == "length":
                    # We have reached the max tokens limit
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'length'"
                    )
                    span.set_attribute("finish_reason", "length")
                    # TODO: saqadri - would be useful to return the reason for stopping to the caller
                    break
                elif choice.finish_reason == "content_filter":
                    # The response was filtered by the content filter
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'content_filter'"
                    )
                    span.set_attribute("finish_reason", "content_filter")
                    # TODO: saqadri - would be useful to return the reason for stopping to the caller
                    break
                elif choice.finish_reason == "stop":
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'stop'"
                    )
                    span.set_attribute("finish_reason", "stop")
                    break

            if params.use_history:
                self.history.set(messages)

            self._log_chat_finished(model=model)

            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, total_input_tokens)
                span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, total_output_tokens)
                span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons)

                for i, res in enumerate(responses):
                    response_data = (
                        self.extract_response_message_attributes_for_tracing(
                            res, prefix=f"response.{i}"
                        )
                    )
                    span.set_attributes(response_data)

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
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_str"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
                self._annotate_span_for_generation_message(span, message)
                if request_params:
                    AugmentedLLM.annotate_span_with_request_params(span, request_params)

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

            res = "\n".join(final_text)
            span.set_attribute("response", res)
            return res

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """
        Use OpenAI native structured outputs via response_format (JSON schema).
        """
        import json

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_structured"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
                self._annotate_span_for_generation_message(span, message)

            params = self.get_request_params(request_params)
            model = await self.select_model(params) or (
                self.default_request_params.model or "gpt-4o"
            )
            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)
                span.set_attribute(GEN_AI_REQUEST_MODEL, model)
                span.set_attribute("response_model", response_model.__name__)

            # Prepare messages
            messages: List[ChatCompletionMessageParam] = []
            system_prompt = self.instruction or params.systemPrompt
            if system_prompt:
                messages.append(
                    ChatCompletionSystemMessageParam(
                        role="system", content=system_prompt
                    )
                )
            if params.use_history:
                messages.extend(self.history.get())
            messages.extend(OpenAIConverter.convert_mixed_messages_to_openai(message))

            # Build response_format
            schema = response_model.model_json_schema()

            # Helpers for OpenAI strict JSON schema handling
            # Strict requires `additionalProperties: false` and `required` include all keys
            def _ensure_no_additional_props_and_require_all(node: dict):
                if not isinstance(node, dict):
                    return
                node_type = node.get("type")
                if node_type == "object":
                    # Enforce no additional properties
                    if "additionalProperties" not in node:
                        node["additionalProperties"] = False
                    # OpenAI strict mode expects 'required' to include every key in 'properties'
                    props = node.get("properties")
                    if isinstance(props, dict):
                        node["required"] = list(props.keys())

                # Recurse into common JSON Schema composition/containers
                for key in ("properties", "$defs", "definitions"):
                    sub = node.get(key)
                    if isinstance(sub, dict):
                        for v in sub.values():
                            _ensure_no_additional_props_and_require_all(v)
                if "items" in node:
                    _ensure_no_additional_props_and_require_all(node["items"])
                for key in ("oneOf", "anyOf", "allOf"):
                    subs = node.get(key)
                    if isinstance(subs, list):
                        for v in subs:
                            _ensure_no_additional_props_and_require_all(v)

            if params.strict:
                _ensure_no_additional_props_and_require_all(schema)

            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": getattr(response_model, "__name__", "StructuredOutput"),
                    "schema": schema,
                    "strict": params.strict,
                },
            }

            # Build payload
            payload = {
                "model": model,
                "messages": messages,
                "response_format": response_format,
            }

            # Use max_completion_tokens for reasoning models, max_tokens for others
            if self._reasoning(model):
                # DEPRECATED: https://platform.openai.com/docs/api-reference/chat/create#chat-create-max_tokens
                # "max_tokens": params.maxTokens,
                payload["max_completion_tokens"] = params.maxTokens
                payload["reasoning_effort"] = self._reasoning_effort
            else:
                payload["max_tokens"] = params.maxTokens
            user = params.user or getattr(self.context.config.openai, "user", None)
            if user:
                payload["user"] = user
            if params.stopSequences is not None:
                payload["stop"] = params.stopSequences
            if params.metadata:
                payload.update(params.metadata)

            completion: ChatCompletion = await self.executor.execute(
                OpenAICompletionTasks.request_completion_task,
                RequestCompletionRequest(
                    config=self.context.config.openai, payload=payload
                ),
            )

            # If the workflow task surfaced an exception, surface it here
            if isinstance(completion, BaseException):
                raise completion

            if not completion.choices or completion.choices[0].message.content is None:
                raise ValueError("No structured content returned by model")

            content = completion.choices[0].message.content
            try:
                data = json.loads(content)
                return response_model.model_validate(data)
            except Exception:
                # Fallback to pydantic JSON parsing if already a JSON string-like
                return response_model.model_validate_json(content)

    async def pre_tool_call(self, tool_call_id: str | None, request: CallToolRequest):
        return request

    async def post_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest, result: CallToolResult
    ):
        return result

    async def execute_tool_call(
        self,
        tool_call: ChatCompletionMessageToolCall,
    ) -> ChatCompletionToolMessageParam:
        """
        Execute a single tool call and return the result message.
        Returns a single ChatCompletionToolMessageParam object.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.execute_tool_call"
        ) as span:
            tool_name = tool_call.function.name
            tool_args_str = tool_call.function.arguments
            tool_call_id = tool_call.id
            tool_args = {}

            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_TOOL_CALL_ID, tool_call_id)
                span.set_attribute(GEN_AI_TOOL_NAME, tool_name)
                span.set_attribute("tool_args", tool_args_str)

            try:
                if tool_args_str:
                    tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
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

            self._annotate_span_for_call_tool_result(span, result)

            return ChatCompletionToolMessageParam(
                role="tool",
                tool_call_id=tool_call_id,
                content=[mcp_content_to_openai_content_part(c) for c in result.content],
            )

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

    def message_str(
        self, message: ChatCompletionMessage, content_only: bool = False
    ) -> str:
        """Convert an output message to a string representation."""
        content = message.content
        if content:
            return content
        elif content_only:
            # If content_only is True, return empty string if no content
            return ""

        return str(message)

    def _annotate_span_for_generation_message(
        self,
        span: trace.Span,
        message: MessageTypes,
    ) -> None:
        """Annotate the span with the message content."""
        if not self.context.tracing_enabled:
            return
        if isinstance(message, str):
            span.set_attribute("message.content", message)
        elif isinstance(message, list):
            for i, msg in enumerate(message):
                if isinstance(msg, str):
                    span.set_attribute(f"message.{i}.content", msg)
                else:
                    span.set_attribute(f"message.{i}", str(msg))
        else:
            span.set_attribute("message", str(message))

    def _extract_message_param_attributes_for_tracing(
        self, message_param: ChatCompletionMessageParam, prefix: str = "message"
    ) -> dict[str, Any]:
        """Return a flat dict of span attributes for a given ChatCompletionMessageParam."""
        attrs = {}
        # TODO: rholinshead - serialize MessageParam dict
        return attrs

    def _annotate_span_for_completion_request(
        self, span: trace.Span, request: RequestCompletionRequest, turn: int
    ) -> None:
        """Annotate the span with the completion request as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.request.turn": turn,
            "config.reasoning_effort": request.config.reasoning_effort,
        }

        if request.config.base_url:
            event_data["config.base_url"] = request.config.base_url

        for key, value in request.payload.items():
            if key == "messages":
                for i, message in enumerate(
                    cast(List[ChatCompletionMessageParam], value)
                ):
                    role = message.get("role")
                    event_data[f"messages.{i}.role"] = role
                    message_content = message.get("content")

                    match role:
                        case "developer" | "system" | "user":
                            if isinstance(message_content, str):
                                event_data[f"messages.{i}.content"] = message_content
                            elif message_content is not None:
                                for j, part in enumerate(message_content):
                                    event_data[f"messages.{i}.content.{j}.type"] = part[
                                        "type"
                                    ]
                                    if part["type"] == "text":
                                        event_data[f"messages.{i}.content.{j}.text"] = (
                                            part["text"]
                                        )
                                    elif part["type"] == "image_url":
                                        event_data[
                                            f"messages.{i}.content.{j}.image_url.url"
                                        ] = part["image_url"]["url"]
                                        event_data[
                                            f"messages.{i}.content.{j}.image_url.detail"
                                        ] = part["image_url"]["detail"]
                                    elif part["type"] == "input_audio":
                                        event_data[
                                            f"messages.{i}.content.{j}.input_audio.format"
                                        ] = part["input_audio"]["format"]
                        case "assistant":
                            if isinstance(message_content, str):
                                event_data[f"messages.{i}.content"] = message_content
                            elif message_content is not None:
                                for j, part in enumerate(message_content):
                                    event_data[f"messages.{i}.content.{j}.type"] = part[
                                        "type"
                                    ]
                                    if part["type"] == "text":
                                        event_data[f"messages.{i}.content.{j}.text"] = (
                                            part["text"]
                                        )
                                    elif part["type"] == "refusal":
                                        event_data[
                                            f"messages.{i}.content.{j}.refusal"
                                        ] = part["refusal"]
                            if message.get("audio") is not None:
                                event_data[f"messages.{i}.audio.id"] = message.get(
                                    "audio"
                                ).get("id")
                            if message.get("function_call") is not None:
                                event_data[f"messages.{i}.function_call.name"] = (
                                    message.get("function_call").get("name")
                                )
                                event_data[f"messages.{i}.function_call.arguments"] = (
                                    message.get("function_call").get("arguments")
                                )
                            if message.get("name") is not None:
                                event_data[f"messages.{i}.name"] = message.get("name")
                            if message.get("refusal") is not None:
                                event_data[f"messages.{i}.refusal"] = message.get(
                                    "refusal"
                                )
                            if message.get("tool_calls") is not None:
                                for j, tool_call in enumerate(
                                    message.get("tool_calls")
                                ):
                                    event_data[
                                        f"messages.{i}.tool_calls.{j}.{GEN_AI_TOOL_CALL_ID}"
                                    ] = tool_call.id
                                    event_data[
                                        f"messages.{i}.tool_calls.{j}.function.name"
                                    ] = tool_call.function.name
                                    event_data[
                                        f"messages.{i}.tool_calls.{j}.function.arguments"
                                    ] = tool_call.function.arguments

                        case "tool":
                            event_data[f"messages.{i}.{GEN_AI_TOOL_CALL_ID}"] = (
                                message.get("tool_call_id")
                            )
                            if isinstance(message_content, str):
                                event_data[f"messages.{i}.content"] = message_content
                            elif message_content is not None:
                                for j, part in enumerate(message_content):
                                    event_data[f"messages.{i}.content.{j}.type"] = part[
                                        "type"
                                    ]
                                    if part["type"] == "text":
                                        event_data[f"messages.{i}.content.{j}.text"] = (
                                            part["text"]
                                        )
                        case "function":
                            event_data[f"messages.{i}.name"] = message.get("name")
                            event_data[f"messages.{i}.content"] = message_content

            elif key == "tools":
                if value is not None:
                    event_data["tools"] = [
                        tool.get("function", {}).get("name") for tool in value
                    ]
            elif is_otel_serializable(value):
                event_data[key] = value

        # Event name is based on the latest message role
        event_name = f"completion.request.{turn}"
        latest_message_role = request.payload.get("messages", [{}])[-1].get("role")

        if latest_message_role:
            event_name = f"gen_ai.{latest_message_role}.message"

        span.add_event(event_name, event_data)

    def _annotate_span_for_completion_response(
        self, span: trace.Span, response: ChatCompletion, turn: int
    ) -> None:
        """Annotate the span with the completion response as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.response.turn": turn,
        }

        event_data.update(
            self._extract_chat_completion_attributes_for_tracing(response)
        )

        # Event name is based on the first choice for now
        event_name = f"completion.response.{turn}"
        if response.choices and len(response.choices) > 0:
            latest_message_role = response.choices[0].message.role
            event_name = f"gen_ai.{latest_message_role}.message"

        span.add_event(event_name, event_data)

    def extract_response_message_attributes_for_tracing(
        self, message: ChatCompletionMessage, prefix: str | None = None
    ) -> Dict[str, Any]:
        """
        Extract relevant attributes from the ChatCompletionMessage for tracing.
        """
        if not self.context.tracing_enabled:
            return {}

        attr_prefix = f"{prefix}." if prefix else ""
        attrs = {
            f"{attr_prefix}role": message.role,
        }

        if message.content is not None:
            attrs[f"{attr_prefix}content"] = message.content

        if message.refusal:
            attrs[f"{attr_prefix}refusal"] = message.refusal
        if message.audio is not None:
            attrs[f"{attr_prefix}audio.id"] = message.audio.id
            attrs[f"{attr_prefix}audio.expires_at"] = message.audio.expires_at
            attrs[f"{attr_prefix}audio.transcript"] = message.audio.transcript
        if message.function_call is not None:
            attrs[f"{attr_prefix}function_call.name"] = message.function_call.name
            attrs[f"{attr_prefix}function_call.arguments"] = (
                message.function_call.arguments
            )
        if message.tool_calls:
            for j, tool_call in enumerate(message.tool_calls):
                attrs[f"{attr_prefix}tool_calls.{j}.{GEN_AI_TOOL_CALL_ID}"] = (
                    tool_call.id
                )
                attrs[f"{attr_prefix}tool_calls.{j}.function.name"] = (
                    tool_call.function.name
                )
                attrs[f"{attr_prefix}tool_calls.{j}.function.arguments"] = (
                    tool_call.function.arguments
                )

        return attrs

    def _extract_chat_completion_attributes_for_tracing(
        self, response: ChatCompletion, prefix: str | None = None
    ) -> Dict[str, Any]:
        """
        Extract relevant attributes from the ChatCompletion response for tracing.
        """
        if not self.context.tracing_enabled:
            return {}

        attr_prefix = f"{prefix}." if prefix else ""
        attrs = {
            f"{attr_prefix}id": response.id,
            f"{attr_prefix}model": response.model,
            f"{attr_prefix}object": response.object,
            f"{attr_prefix}created": response.created,
        }

        if response.service_tier:
            attrs[f"{attr_prefix}service_tier"] = response.service_tier

        if response.system_fingerprint:
            attrs[f"{attr_prefix}system_fingerprint"] = response.system_fingerprint

        if response.usage:
            attrs[f"{attr_prefix}{GEN_AI_USAGE_INPUT_TOKENS}"] = (
                response.usage.prompt_tokens
            )
            attrs[f"{attr_prefix}{GEN_AI_USAGE_OUTPUT_TOKENS}"] = (
                response.usage.completion_tokens
            )

        finish_reasons = []
        for i, choice in enumerate(response.choices):
            attrs[f"{attr_prefix}choices.{i}.index"] = choice.index
            attrs[f"{attr_prefix}choices.{i}.finish_reason"] = choice.finish_reason
            finish_reasons.append(choice.finish_reason)

            message_attrs = self.extract_response_message_attributes_for_tracing(
                choice.message, f"{attr_prefix}choices.{i}.message"
            )
            attrs.update(message_attrs)

        attrs[GEN_AI_RESPONSE_FINISH_REASONS] = finish_reasons

        return attrs


class OpenAICompletionTasks:
    @staticmethod
    @workflow_task
    @telemetry.traced()
    async def request_completion_task(
        request: RequestCompletionRequest,
    ) -> ChatCompletion:
        """
        Request a completion from OpenAI's API.
        """
        async with AsyncOpenAI(
            api_key=request.config.api_key,
            base_url=request.config.base_url,
            http_client=request.config.http_client
            if hasattr(request.config, "http_client")
            else None,
            default_headers=request.config.default_headers
            if hasattr(request.config, "default_headers")
            else None,
        ) as async_openai_client:
            payload = request.payload
            response = await async_openai_client.chat.completions.create(**payload)
            response = ensure_serializable(response)
            return response

    @staticmethod
    @workflow_task
    @telemetry.traced()
    async def request_structured_completion_task(
        request: RequestStructuredCompletionRequest,
    ) -> ModelT:
        """
        Request a structured completion using OpenAI's native structured outputs.
        """
        # Resolve the response model
        if request.response_model is not None:
            response_model = request.response_model
        elif request.serialized_response_model is not None:
            response_model = deserialize_model(request.serialized_response_model)
        else:
            raise ValueError(
                "Either response_model or serialized_response_model must be provided for structured completion."
            )

        # Build response_format using JSON Schema
        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": getattr(response_model, "__name__", "StructuredOutput"),
                "schema": schema,
                "strict": request.strict,
            },
        }

        async with AsyncOpenAI(
            api_key=request.config.api_key,
            base_url=request.config.base_url,
            http_client=request.config.http_client
            if hasattr(request.config, "http_client")
            else None,
            default_headers=request.config.default_headers
            if hasattr(request.config, "default_headers")
            else None,
        ) as async_openai_client:
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.response_str}],
                "response_format": response_format,
            }
            if request.user:
                payload["user"] = request.user

            completion = await async_openai_client.chat.completions.create(**payload)

            if not completion.choices or completion.choices[0].message.content is None:
                raise ValueError("No structured content returned by model")

            content = completion.choices[0].message.content
            # message.content is expected to be JSON string
            try:
                data = json.loads(content)
            except Exception:
                # Some models may already return a dict-like; fall back to string validation
                return response_model.model_validate_json(content)

            return response_model.model_validate(data)


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
        return ChatCompletionContentPartImageParam(
            type="image_url",
            image_url={"url": f"data:{content.mimeType};base64,{content.data}"},
        )
    elif isinstance(content, EmbeddedResource):
        if isinstance(content.resource, TextResourceContents):
            return ChatCompletionContentPartTextParam(
                type="text", text=content.resource.text
            )
        else:  # BlobResourceContents
            if content.resource.mimeType and content.resource.mimeType.startswith(
                "image/"
            ):
                return ChatCompletionContentPartImageParam(
                    type="image_url",
                    image_url={
                        "url": f"data:{content.resource.mimeType};base64,{content.resource.blob}"
                    },
                )
            else:
                # Best effort if mime type is unknown
                return ChatCompletionContentPartTextParam(
                    type="text",
                    text=f"{content.resource.mimeType}:{content.resource.blob}",
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
            if (
                c["type"] == "text"
            ):  # isinstance(c, ChatCompletionContentPartTextParam):
                mcp_content.append(
                    TextContent(
                        type="text", text=c["text"], **typed_dict_extras(c, ["text"])
                    )
                )
            elif (
                c["type"] == "image_url"
            ):  # isinstance(c, ChatCompletionContentPartImageParam):
                if c["image_url"].startswith("data:"):
                    mime_type, base64_data = image_url_to_mime_and_base64(
                        c["image_url"]
                    )
                    mcp_content.append(
                        ImageContent(type="image", data=base64_data, mimeType=mime_type)
                    )
                else:
                    # TODO: saqadri - need to download the image into a base64-encoded string
                    raise NotImplementedError(
                        "Image content conversion not implemented"
                    )
            elif (
                c["type"] == "input_audio"
            ):  # isinstance(c, ChatCompletionContentPartInputAudioParam):
                raise NotImplementedError("Audio content conversion not implemented")
            elif (
                c["type"] == "refusal"
            ):  # isinstance(c, ChatCompletionContentPartRefusalParam):
                mcp_content.append(
                    TextContent(
                        type="text",
                        text=c["refusal"],
                        **typed_dict_extras(c, ["refusal"]),
                    )
                )
            else:
                raise ValueError(f"Unexpected content type: {c['type']}")

    return mcp_content
