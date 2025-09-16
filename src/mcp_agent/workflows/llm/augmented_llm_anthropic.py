import asyncio
import functools
from typing import Any, Iterable, List, Type, Union, cast

from pydantic import BaseModel

from anthropic import Anthropic, AnthropicBedrock, AnthropicVertex, AsyncAnthropic
from anthropic.types import (
    ContentBlock,
    DocumentBlockParam,
    Message,
    MessageParam,
    ImageBlockParam,
    TextBlock,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
    Base64ImageSourceParam,
    PlainTextSourceParam,
    Base64PDFSourceParam,
    ThinkingBlockParam,
    RedactedThinkingBlockParam,
)
from opentelemetry import trace
from mcp.types import (
    CallToolRequestParams,
    CallToolRequest,
    EmbeddedResource,
    ImageContent,
    ModelPreferences,
    StopReason,
    TextContent,
    TextResourceContents,
)

# from mcp_agent import console
# from mcp_agent.agents.agent import HUMAN_INPUT_TOOL_NAME
from mcp_agent.config import AnthropicSettings
from mcp_agent.executor.workflow_task import workflow_task
from mcp_agent.tracing.semconv import (
    GEN_AI_AGENT_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)
from mcp_agent.tracing.telemetry import get_tracer, is_otel_serializable, telemetry
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.utils.common import ensure_serializable, typed_dict_extras, to_string

from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    ModelT,
    MCPMessageParam,
    MCPMessageResult,
    ProviderToMCPConverter,
    RequestParams,
    CallToolResult,
)
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.multipart_converter_anthropic import AnthropicConverter

MessageParamContent = Union[
    str,
    Iterable[
        Union[
            TextBlockParam,
            ImageBlockParam,
            ToolUseBlockParam,
            ToolResultBlockParam,
            DocumentBlockParam,
            ThinkingBlockParam,
            RedactedThinkingBlockParam,
            ContentBlock,
        ]
    ],
]


class RequestCompletionRequest(BaseModel):
    config: AnthropicSettings
    payload: dict


def create_anthropic_instance(settings: AnthropicSettings):
    """Select and initialise the appropriate anthropic client instance based on settings"""
    if settings.provider == "bedrock":
        anthropic = AnthropicBedrock(
            aws_access_key=settings.aws_access_key_id,
            aws_secret_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token,
            aws_region=settings.aws_region,
        )
    elif settings.provider == "vertexai":
        anthropic = AnthropicVertex(
            region=settings.location,
            project_id=settings.project,
        )
    else:
        anthropic = Anthropic(api_key=settings.api_key)
    return anthropic


class AnthropicAugmentedLLM(AugmentedLLM[MessageParam, Message]):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    Our current models can actively use these capabilities—generating their own search queries,
    selecting appropriate tools, and determining what information to retain.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            type_converter=AnthropicMCPTypeConverter,
            **kwargs,
        )

        self.provider = "Anthropic"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )

        default_model = "claude-sonnet-4-20250514"

        if self.context.config.anthropic:
            self.provider = self.context.config.anthropic.provider
            if self.context.config.anthropic.provider == "bedrock":
                default_model = "anthropic.claude-sonnet-4-20250514-v1:0"
            elif self.context.config.anthropic.provider == "vertexai":
                default_model = "claude-sonnet-4@20250514"

            if hasattr(self.context.config.anthropic, "default_model"):
                default_model = self.context.config.anthropic.default_model

        self.default_request_params = self.default_request_params or RequestParams(
            model=default_model,
            modelPreferences=self.model_preferences,
            maxTokens=2048,
            systemPrompt=self.instruction,
            parallel_tool_calls=False,
            max_iterations=10,
            use_history=True,
        )

    @track_tokens()
    async def generate(
        self,
        message,
        request_params: RequestParams | None = None,
    ):
        """
        Process a query using an LLM and available tools.
        The default implementation uses Claude as the LLM.
        Override this method to use a different LLM.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            self._annotate_span_for_generation_message(span, message)

            config = self.context.config
            messages: List[MessageParam] = []
            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            if params.use_history:
                messages.extend(self.history.get())
            messages.extend(
                AnthropicConverter.convert_mixed_messages_to_anthropic(message)
            )

            list_tools_result = await self.agent.list_tools(
                tool_filter=params.tool_filter
            )
            available_tools: List[ToolParam] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in list_tools_result.tools
            ]

            responses: List[Message] = []
            model = await self.select_model(params)

            if model:
                span.set_attribute(GEN_AI_REQUEST_MODEL, model)

            total_input_tokens = 0
            total_output_tokens = 0
            finish_reasons = []

            for i in range(params.max_iterations):
                if (
                    i == params.max_iterations - 1
                    and responses
                    and responses[-1].stop_reason == "tool_use"
                ):
                    final_prompt_message = MessageParam(
                        role="user",
                        content="""We've reached the maximum number of iterations. 
                        Please stop using tools now and provide your final comprehensive answer based on all tool results so far. 
                        At the beginning of your response, clearly indicate that your answer may be incomplete due to reaching the maximum number of tool usage iterations, 
                        and explain what additional information you would have needed to provide a more complete answer.""",
                    )
                    messages.append(final_prompt_message)

                arguments = {
                    "model": model,
                    "max_tokens": params.maxTokens,
                    "messages": messages,
                    "stop_sequences": params.stopSequences or [],
                    "tools": available_tools,
                }

                if system := (self.instruction or params.systemPrompt):
                    arguments["system"] = system

                if params.metadata:
                    arguments = {**arguments, **params.metadata}

                self.logger.debug("Completion request arguments:", data=arguments)
                self._log_chat_progress(chat_turn=(len(messages) + 1) // 2, model=model)

                request = RequestCompletionRequest(
                    config=config.anthropic,
                    payload=arguments,
                )

                self._annotate_span_for_completion_request(span, request, i)

                response: Message = await self.executor.execute(
                    AnthropicCompletionTasks.request_completion_task,
                    ensure_serializable(request),
                )

                if isinstance(response, BaseException):
                    self.logger.error(f"Error: {response}")
                    span.record_exception(response)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    break

                self.logger.debug(
                    f"{model} response:",
                    data=response,
                )

                self._annotate_span_for_completion_response(span, response, i)

                # Per-iteration token counts
                iteration_input = response.usage.input_tokens
                iteration_output = response.usage.output_tokens

                total_input_tokens += iteration_input
                total_output_tokens += iteration_output

                response_as_message = self.convert_message_to_message_param(response)
                messages.append(response_as_message)
                responses.append(response)
                finish_reasons.append(response.stop_reason)

                # Incremental token tracking inside loop so watchers update during long runs
                if self.context.token_counter:
                    await self.context.token_counter.record_usage(
                        input_tokens=iteration_input,
                        output_tokens=iteration_output,
                        model_name=model,
                        provider=self.provider,
                    )

                if response.stop_reason == "end_turn":
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'end_turn'"
                    )
                    span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, ["end_turn"])
                    break
                elif response.stop_reason == "stop_sequence":
                    # We have reached a stop sequence
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'stop_sequence'"
                    )
                    span.set_attribute(
                        GEN_AI_RESPONSE_FINISH_REASONS, ["stop_sequence"]
                    )
                    break
                elif response.stop_reason == "max_tokens":
                    # We have reached the max tokens limit
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is 'max_tokens'"
                    )
                    span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, ["max_tokens"])
                    # TODO: saqadri - would be useful to return the reason for stopping to the caller
                    break
                else:  # response.stop_reason == "tool_use":
                    for content in response.content:
                        if content.type == "tool_use":
                            tool_name = content.name
                            tool_args = content.input
                            tool_use_id = content.id

                            # TODO -- productionize this
                            # if tool_name == HUMAN_INPUT_TOOL_NAME:
                            #     # Get the message from the content list
                            #     message_text = ""
                            #     for block in response_as_message["content"]:
                            #         if (
                            #             isinstance(block, dict)
                            #             and block.get("type") == "text"
                            #         ):
                            #             message_text += block.get("text", "")
                            #         elif hasattr(block, "type") and block.type == "text":
                            #             message_text += block.text

                            # panel = Panel(
                            #     message_text,
                            #     title="MESSAGE",
                            #     style="green",
                            #     border_style="bold white",
                            #     padding=(1, 2),
                            # )
                            # console.console.print(panel)

                            tool_call_request = CallToolRequest(
                                method="tools/call",
                                params=CallToolRequestParams(
                                    name=tool_name, arguments=tool_args
                                ),
                            )

                            result = await self.call_tool(
                                request=tool_call_request, tool_call_id=tool_use_id
                            )

                            message = self.from_mcp_tool_result(result, tool_use_id)

                            messages.append(message)

            if params.use_history:
                self.history.set(messages)

            self._log_chat_finished(model=model)

            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, total_input_tokens)
                span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, total_output_tokens)
                span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons)

                for i, response in enumerate(responses):
                    response_data = (
                        self.extract_response_message_attributes_for_tracing(
                            response, prefix=f"response.{i}"
                        )
                    )
                    span.set_attributes(response_data)

            return responses

    async def generate_str(
        self,
        message,
        request_params: RequestParams | None = None,
    ) -> str:
        """
        Process a query using an LLM and available tools.
        The default implementation uses Claude as the LLM.
        Override this method to use a different LLM.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_str"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            self._annotate_span_for_generation_message(span, message)
            if self.context.tracing_enabled and request_params:
                AugmentedLLM.annotate_span_with_request_params(span, request_params)

            responses: List[Message] = await self.generate(
                message=message,
                request_params=request_params,
            )

            final_text: List[str] = []

            for response in responses:
                for content in response.content:
                    if content.type == "text":
                        final_text.append(content.text)
                    elif content.type == "tool_use":
                        final_text.append(
                            f"[Calling tool {content.name} with args {content.input}]"
                        )

            res = "\n".join(final_text)
            span.set_attribute("response", res)
            return res

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        # Use Anthropic's native structured output via a forced tool call carrying JSON input
        import json

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_structured"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            self._annotate_span_for_generation_message(span, message)

            params = self.get_request_params(request_params)
            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            model_name = (
                await self.select_model(params) or self.default_request_params.model
            )
            span.set_attribute(GEN_AI_REQUEST_MODEL, model_name)

            # Convert message(s) to Anthropic format
            messages: List[MessageParam] = []
            if params.use_history:
                messages.extend(self.history.get())
            messages.extend(
                AnthropicConverter.convert_mixed_messages_to_anthropic(message)
            )

            # Define a single tool that matches the Pydantic schema
            schema = response_model.model_json_schema()
            tools: List[ToolParam] = [
                {
                    "name": "return_structured_output",
                    "description": "Return the response in the required JSON format",
                    "input_schema": schema,
                }
            ]

            args = {
                "model": model_name,
                "messages": messages,
                "system": self.instruction or params.systemPrompt,
                "tools": tools,
                "tool_choice": {"type": "tool", "name": "return_structured_output"},
            }
            if params.maxTokens is not None:
                args["max_tokens"] = params.maxTokens
            if params.stopSequences:
                args["stop_sequences"] = params.stopSequences

            # Call Anthropic directly (one-turn streaming for consistency)
            base_url = None
            if self.context and self.context.config and self.context.config.anthropic:
                base_url = self.context.config.anthropic.base_url
                api_key = self.context.config.anthropic.api_key
                client = AsyncAnthropic(api_key=api_key, base_url=base_url)
            else:
                client = AsyncAnthropic()

            async with client:
                async with client.messages.stream(**args) as stream:
                    final = await stream.get_final_message()

            # Extract tool_use input and validate
            for block in final.content:
                if (
                    getattr(block, "type", None) == "tool_use"
                    and getattr(block, "name", "") == "return_structured_output"
                ):
                    data = getattr(block, "input", None)
                    try:
                        if isinstance(data, str):
                            return response_model.model_validate(json.loads(data))
                        return response_model.model_validate(data)
                    except Exception:
                        # Fallthrough to error
                        break

            raise ValueError(
                "Failed to obtain structured output from Anthropic response"
            )

    @classmethod
    def convert_message_to_message_param(
        cls, message: Message, **kwargs
    ) -> MessageParam:
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        content = []

        for content_block in message.content:
            if content_block.type == "text":
                content.append(TextBlockParam(type="text", text=content_block.text))
            elif content_block.type == "tool_use":
                content.append(
                    ToolUseBlockParam(
                        type="tool_use",
                        name=content_block.name,
                        input=content_block.input,
                        id=content_block.id,
                    )
                )

        return MessageParam(role="assistant", content=content, **kwargs)

    def message_param_str(self, message: MessageParam) -> str:
        """Convert an input message to a string representation."""

        if message.get("content"):
            content = message["content"]
            if isinstance(content, str):
                return content
            else:
                final_text: List[str] = []
                for block in content:
                    if block.text:
                        final_text.append(str(block.text))
                    else:
                        final_text.append(str(block))

                return "\n".join(final_text)

        return str(message)

    def message_str(self, message: Message, content_only: bool = False) -> str:
        """Convert an output message to a string representation."""
        content = message.content

        if content:
            if isinstance(content, list):
                final_text: List[str] = []
                for block in content:
                    if block.text:
                        final_text.append(str(block.text))
                    else:
                        final_text.append(str(block))

                return "\n".join(final_text)
            else:
                return str(content)
        elif content_only:
            # If content_only is True, we return an empty string if there's no content
            return ""

        return str(message)

    def _extract_message_param_attributes_for_tracing(
        self, message_param: MessageParam, prefix: str = "message"
    ) -> dict[str, Any]:
        """Return a flat dict of span attributes for a given MessageParam."""
        if not self.context.tracing_enabled:
            return {}

        attrs = {}
        attrs[f"{prefix}.role"] = message_param.get("role")
        message_content = message_param.get("content")

        if isinstance(message_content, str):
            attrs[f"{prefix}.content"] = message_content

        elif isinstance(message_content, list):
            for j, part in enumerate(message_content):
                message_content_prefix = f"{prefix}.content.{j}"
                attrs[f"{message_content_prefix}.type"] = part.get("type")

                match part.get("type"):
                    case "text":
                        attrs[f"{message_content_prefix}.text"] = part.get("text")
                    case "image":
                        source_type = part.get("source", {}).get("type")
                        attrs[f"{message_content_prefix}.source.type"] = source_type
                        if source_type == "base64":
                            attrs[f"{message_content_prefix}.source.media_type"] = (
                                part.get("source", {}).get("media_type")
                            )
                        elif source_type == "url":
                            attrs[f"{message_content_prefix}.source.url"] = part.get(
                                "source", {}
                            ).get("url")
                    case "tool_use":
                        attrs[f"{message_content_prefix}.id"] = part.get("id")
                        attrs[f"{message_content_prefix}.name"] = part.get("name")
                    case "tool_result":
                        attrs[f"{message_content_prefix}.tool_use_id"] = part.get(
                            "tool_use_id"
                        )
                        attrs[f"{message_content_prefix}.is_error"] = part.get(
                            "is_error"
                        )
                        part_content = part.get("content")
                        if isinstance(part_content, str):
                            attrs[f"{message_content_prefix}.content"] = part_content
                        elif isinstance(part_content, list):
                            for k, sub_part in enumerate(part_content):
                                sub_part_type = sub_part.get("type")
                                if sub_part_type == "text":
                                    attrs[
                                        f"{message_content_prefix}.content.{k}.text"
                                    ] = sub_part.get("text")
                                elif sub_part_type == "image":
                                    sub_part_source = sub_part.get("source")
                                    sub_part_source_type = sub_part_source.get("type")
                                    attrs[
                                        f"{message_content_prefix}.content.{k}.source.type"
                                    ] = sub_part_source_type
                                    if sub_part_source_type == "base64":
                                        attrs[
                                            f"{message_content_prefix}.content.{k}.source.media_type"
                                        ] = sub_part_source.get("media_type")
                                    elif sub_part_source_type == "url":
                                        attrs[
                                            f"{message_content_prefix}.content.{k}.source.url"
                                        ] = sub_part_source.get("url")
                    case "document":
                        if part.get("context") is not None:
                            attrs[f"{message_content_prefix}.context"] = part.get(
                                "context"
                            )
                        if part.get("title") is not None:
                            attrs[f"{message_content_prefix}.title"] = part.get("title")
                        if part.get("citations") is not None:
                            attrs[f"{message_content_prefix}.citations.enabled"] = (
                                part.get("citations").get("enabled")
                            )
                        part_source_type = part.get("source", {}).get("type")
                        attrs[f"{message_content_prefix}.source.type"] = (
                            part_source_type
                        )
                        if part_source_type == "text":
                            attrs[f"{message_content_prefix}.source.data"] = part.get(
                                "source", {}
                            ).get("data")
                        elif part_source_type == "url":
                            attrs[f"{message_content_prefix}.source.url"] = part.get(
                                "source", {}
                            ).get("url")
                    case "thinking":
                        attrs[f"{message_content_prefix}.thinking"] = part.get(
                            "thinking"
                        )
                        attrs[f"{message_content_prefix}.signature"] = part.get(
                            "signature"
                        )
                    case "redacted_thinking":
                        attrs[f"{message_content_prefix}.redacted_thinking"] = part.get(
                            "data"
                        )
        return attrs

    def extract_response_message_attributes_for_tracing(
        self, message: Message, prefix: str | None = None
    ) -> dict[str, Any]:
        """Return a flat dict of span attributes for a given Message."""
        if not self.context.tracing_enabled:
            return {}

        attr_prefix = f"{prefix}." if prefix else ""
        attrs = {
            f"{attr_prefix}id": message.id,
            f"{attr_prefix}model": message.model,
            f"{attr_prefix}role": message.role,
        }

        if message.stop_reason:
            attrs[f"{attr_prefix}{GEN_AI_RESPONSE_FINISH_REASONS}"] = [
                message.stop_reason
            ]
        if message.stop_sequence:
            attrs[f"{attr_prefix}stop_sequence"] = message.stop_sequence
        if message.usage:
            attrs[f"{attr_prefix}{GEN_AI_USAGE_INPUT_TOKENS}"] = (
                message.usage.input_tokens
            )
            attrs[f"{attr_prefix}{GEN_AI_USAGE_OUTPUT_TOKENS}"] = (
                message.usage.output_tokens
            )

        for i, block in enumerate(message.content):
            attrs[f"{attr_prefix}content.{i}.type"] = block.type
            match block.type:
                case "text":
                    attrs[f"{attr_prefix}content.{i}.text"] = block.text
                case "tool_use":
                    attrs[f"{attr_prefix}content.{i}.tool_use_id"] = block.id
                    attrs[f"{attr_prefix}content.{i}.name"] = block.name
                case "thinking":
                    attrs[f"{attr_prefix}content.{i}.thinking"] = block.thinking
                    attrs[f"{attr_prefix}content.{i}.signature"] = block.signature
                case "redacted_thinking":
                    attrs[f"{attr_prefix}content.{i}.redacted_thinking"] = block.data
        return attrs

    def _annotate_span_for_completion_request(
        self, span: trace.Span, request: RequestCompletionRequest, turn: int
    ):
        """Annotate the span with the completion request as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.request.turn": turn,
        }

        for key, value in request.payload.items():
            if key == "messages":
                for i, message in enumerate(cast(List[MessageParam], value)):
                    event_data.update(
                        self._extract_message_param_attributes_for_tracing(
                            message, prefix=f"messages.{i}"
                        )
                    )

            elif key == "tools":
                if value is not None:
                    event_data["tools"] = [tool.get("name") for tool in value]

            elif is_otel_serializable(value):
                event_data[key] = value

        # Event name is based on the latest message role
        event_name = f"completion.request.{turn}"
        latest_message_role = request.payload.get("messages", [{}])[-1].get("role")

        if latest_message_role:
            event_name = f"gen_ai.{latest_message_role}.message"

        span.add_event(event_name, event_data)

    def _annotate_span_for_completion_response(
        self, span: trace.Span, response: Message, turn: int
    ):
        """Annotate the span with the completion response as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.response.turn": turn,
        }
        event_data.update(
            self.extract_response_message_attributes_for_tracing(response)
        )
        span.add_event(f"gen_ai.{response.role}.message", event_data)


class AnthropicCompletionTasks:
    @staticmethod
    @workflow_task
    @telemetry.traced()
    async def request_completion_task(
        request: RequestCompletionRequest,
    ) -> Message:
        """
        Request a completion from Anthropic's API.
        """
        # Prefer async client where available to avoid blocking the event loop
        if request.config.provider in (None, "", "anthropic"):
            client = AsyncAnthropic(api_key=request.config.api_key)
            payload = request.payload
            response = await client.messages.create(**payload)
            response = ensure_serializable(response)
            return response
        else:
            anthropic = create_anthropic_instance(request.config)
            payload = request.payload
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, functools.partial(anthropic.messages.create, **payload)
            )
            response = ensure_serializable(response)
            return response


class AnthropicMCPTypeConverter(ProviderToMCPConverter[MessageParam, Message]):
    """
    Convert between Anthropic and MCP types.
    """

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> Message:
        # MCPMessageResult -> Message
        if result.role != "assistant":
            raise ValueError(
                f"Expected role to be 'assistant' but got '{result.role}' instead."
            )

        return Message(
            role="assistant",
            type="message",
            content=[mcp_content_to_anthropic_content(result.content)],
            model=result.model,
            stop_reason=mcp_stop_reason_to_anthropic_stop_reason(result.stopReason),
            id=result.id or None,
            usage=result.usage or None,
            # TODO: should we push extras?
        )

    @classmethod
    def to_mcp_message_result(cls, result: Message) -> MCPMessageResult:
        # Message -> MCPMessageResult

        contents = anthropic_content_to_mcp_content(result.content)
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported in MCP yet"
            )
        mcp_content = contents[0]

        return MCPMessageResult(
            role=result.role,
            content=mcp_content,
            model=result.model,
            stopReason=anthropic_stop_reason_to_mcp_stop_reason(result.stop_reason),
            # extras for Message fields
            **result.model_dump(exclude={"role", "content", "model", "stop_reason"}),
        )

    @classmethod
    def from_mcp_message_param(cls, param: MCPMessageParam) -> MessageParam:
        # MCPMessageParam -> MessageParam
        extras = param.model_dump(exclude={"role", "content"})
        return MessageParam(
            role=param.role,
            content=[
                mcp_content_to_anthropic_content(param.content, for_message_param=True)
            ],
            **extras,
        )

    @classmethod
    def to_mcp_message_param(cls, param: MessageParam) -> MCPMessageParam:
        # Implement the conversion from ChatCompletionMessage to MCP message param

        contents = anthropic_content_to_mcp_content(param.content)

        # TODO: saqadri - the mcp_content can have multiple elements
        # while sampling message content has a single content element
        # Right now we error out if there are > 1 elements in mcp_content
        # We need to handle this case properly going forward
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported"
            )
        mcp_content = contents[0]

        return MCPMessageParam(
            role=param.role,
            content=mcp_content,
            **typed_dict_extras(param, ["role", "content"]),
        )

    @classmethod
    def from_mcp_tool_result(
        cls, result: CallToolResult, tool_use_id: str
    ) -> MessageParam:
        """Convert mcp tool result to user MessageParam"""
        tool_result_block_content: list[TextBlockParam | ImageBlockParam] = []

        for content in result.content:
            converted_content = mcp_content_to_anthropic_content(
                content, for_message_param=True
            )
            if converted_content["type"] in ["text", "image"]:
                tool_result_block_content.append(converted_content)

        if not tool_result_block_content:
            # If no valid content, return as error
            tool_result_block_content = [
                TextBlockParam(type="text", text="No result returned")
            ]
            result.isError = True

        return MessageParam(
            role="user",
            content=[
                ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=tool_use_id,
                    content=tool_result_block_content,
                    is_error=result.isError,
                )
            ],
        )


def mcp_content_to_anthropic_content(
    content: TextContent | ImageContent | EmbeddedResource,
    for_message_param: bool = False,
) -> ContentBlock | MessageParamContent:
    """
    Converts MCP content types into Anthropic-compatible content blocks.

    Args:
        content (TextContent | ImageContent | EmbeddedResource): The MCP content to convert.
        for_message_param (bool, optional): If True, returns Anthropic message param content types.
                                    If False, returns Anthropic response message content types.
                                    Defaults to False.

    Returns:
        ContentBlock: The converted content block in Anthropic format.
    """
    if for_message_param:
        if isinstance(content, TextContent):
            return TextBlockParam(type="text", text=content.text)
        elif isinstance(content, ImageContent):
            return ImageBlockParam(
                type="image",
                source=Base64ImageSourceParam(
                    type="base64",
                    data=content.data,
                    media_type=content.mimeType,
                ),
            )
        elif isinstance(content, EmbeddedResource):
            if isinstance(content.resource, TextResourceContents):
                return TextBlockParam(type="text", text=content.resource.text)
            else:
                if content.resource.mimeType == "text/plain":
                    source = PlainTextSourceParam(
                        type="text",
                        data=content.resource.blob,
                        mimeType=content.resource.mimeType,
                    )
                elif content.resource.mimeType == "application/pdf":
                    source = Base64PDFSourceParam(
                        type="base64",
                        data=content.resource.blob,
                        mimeType=content.resource.mimeType,
                    )
                else:
                    # Best effort to convert
                    return TextBlockParam(
                        type="text",
                        text=f"{content.resource.mimeType}:{content.resource.blob}",
                    )
                return DocumentBlockParam(
                    type="document",
                    source=source,
                )
    else:
        if isinstance(content, TextContent):
            return TextBlock(type=content.type, text=content.text)
        elif isinstance(content, ImageContent):
            # Best effort to convert an image to text (since there's no ImageBlock)
            return TextBlock(type="text", text=f"{content.mimeType}:{content.data}")
        elif isinstance(content, EmbeddedResource):
            if isinstance(content.resource, TextResourceContents):
                return TextBlock(type="text", text=content.resource.text)
            else:  # BlobResourceContents
                return TextBlock(
                    type="text",
                    text=f"{content.resource.mimeType}:{content.resource.blob}",
                )
        else:
            # Last effort to convert the content to a string
            return TextBlock(type="text", text=str(content))


def anthropic_content_to_mcp_content(
    content: str
    | Iterable[
        TextBlockParam
        | ImageBlockParam
        | ToolUseBlockParam
        | ToolResultBlockParam
        | DocumentBlockParam
        | ContentBlock
    ],
) -> List[TextContent | ImageContent | EmbeddedResource]:
    mcp_content = []

    if isinstance(content, str):
        mcp_content.append(TextContent(type="text", text=content))
    else:
        for block in content:
            # Handle pydantic models (ContentBlock) and dict blocks
            if isinstance(block, BaseModel):
                block_type = block.type
                block_text = block.text
            else:
                block_type = block["type"]
                block_text = block["text"]

            if block_type == "text":
                mcp_content.append(TextContent(type="text", text=block_text))
            elif block_type == "image":
                raise NotImplementedError("Image content conversion not implemented")
            elif block_type == "tool_use" or block_type == "tool_result":
                # Best effort to convert a tool use and tool result to text (since there's no ToolUseContent or ToolResultContent)
                mcp_content.append(
                    TextContent(
                        type="text",
                        text=to_string(block),
                    )
                )
            elif block_type == "document":
                raise NotImplementedError("Document content conversion not implemented")
            else:
                # Last effort to convert the content to a string
                mcp_content.append(TextContent(type="text", text=str(block)))

    return mcp_content


def mcp_stop_reason_to_anthropic_stop_reason(stop_reason: StopReason):
    if not stop_reason:
        return None
    elif stop_reason == "endTurn":
        return "end_turn"
    elif stop_reason == "maxTokens":
        return "max_tokens"
    elif stop_reason == "stopSequence":
        return "stop_sequence"
    elif stop_reason == "toolUse":
        return "tool_use"
    else:
        return stop_reason


def anthropic_stop_reason_to_mcp_stop_reason(stop_reason: str) -> StopReason:
    if not stop_reason:
        return None
    elif stop_reason == "end_turn":
        return "endTurn"
    elif stop_reason == "max_tokens":
        return "maxTokens"
    elif stop_reason == "stop_sequence":
        return "stopSequence"
    elif stop_reason == "tool_use":
        return "toolUse"
    else:
        return stop_reason
