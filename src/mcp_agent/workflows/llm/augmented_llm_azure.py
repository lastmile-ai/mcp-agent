import asyncio
import functools
import json
from typing import Any, Iterable, Optional, Type, Union
from azure.core.exceptions import HttpResponseError
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    ChatCompletions,
    ChatResponseMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    DeveloperMessage,
    SystemMessage,
    ChatCompletionsToolDefinition,
    FunctionDefinition,
    CompletionsFinishReason,
    ChatCompletionsToolCall,
    JsonSchemaFormat,
    ContentItem,
    TextContentItem,
    ImageContentItem,
    AudioContentItem,
    ImageUrl,
    ChatRole,
)
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from opentelemetry import trace

from pydantic import BaseModel

from mcp.types import (
    CallToolRequestParams,
    CallToolRequest,
    EmbeddedResource,
    ImageContent,
    ModelPreferences,
    TextContent,
    TextResourceContents,
)

from mcp_agent.config import AzureSettings
from mcp_agent.executor.workflow_task import workflow_task
from mcp_agent.tracing.semconv import (
    GEN_AI_AGENT_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.utils.common import typed_dict_extras
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    ModelT,
    MCPMessageParam,
    MCPMessageResult,
    ProviderToMCPConverter,
    RequestParams,
)
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.multipart_converter_azure import AzureConverter

MessageParam = Union[
    SystemMessage, UserMessage, AssistantMessage, ToolMessage, DeveloperMessage
]


class RequestCompletionRequest(BaseModel):
    config: AzureSettings
    payload: dict


class ResponseMessage(ChatResponseMessage):
    """
    A subclass of ChatResponseMessage that makes 'content' to be optional.

    This accommodates cases where the assistant response includes tool calls
    without a textual message, in which 'content' may be None.
    """

    content: Optional[str]


class AzureAugmentedLLM(AugmentedLLM[MessageParam, ResponseMessage]):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, type_converter=MCPAzureTypeConverter, **kwargs)

        self.provider = "Azure"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )

        # Get default model from config if available
        default_model = "gpt-4o-mini"  # Fallback default

        if self.context.config.azure:
            if hasattr(self.context.config.azure, "default_model"):
                default_model = self.context.config.azure.default_model

        if not self.context.config.azure:
            self.logger.error(
                "Azure configuration not found. Please provide Azure configuration."
            )
            raise ValueError(
                "Azure configuration not found. Please provide Azure configuration."
            )

        self.default_request_params = self.default_request_params or RequestParams(
            model=default_model,
            modelPreferences=self.model_preferences,
            maxTokens=4096,
            systemPrompt=self.instruction,
            parallel_tool_calls=True,
            max_iterations=10,
            use_history=True,
        )

    @track_tokens()
    async def generate(self, message, request_params: RequestParams | None = None):
        """
        Process a query using an LLM and available tools.
        The default implementation uses Azure OpenAI 5 as the LLM.
        Override this method to use a different LLM.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(f"llm_azure.{self.name}.generate") as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            self._annotate_span_for_generation_message(span, message)

            messages: list[MessageParam] = []
            responses: list[ResponseMessage] = []

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            if params.use_history:
                span.set_attribute("use_history", params.use_history)
                messages.extend(self.history.get())

            system_prompt = self.instruction or params.systemPrompt

            if system_prompt and len(messages) == 0:
                messages.append(SystemMessage(content=system_prompt))
                span.set_attribute("system_prompt", system_prompt)

            messages.extend(AzureConverter.convert_mixed_messages_to_azure(message))

            response = await self.agent.list_tools(tool_filter=params.tool_filter)

            tools: list[ChatCompletionsToolDefinition] = [
                ChatCompletionsToolDefinition(
                    function=FunctionDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.inputSchema,
                    )
                )
                for tool in response.tools
            ]

            span.set_attribute(
                "available_tools",
                [t.function.name for t in tools],
            )

            model = await self.select_model(params)
            if model:
                span.set_attribute(GEN_AI_REQUEST_MODEL, model)

            total_input_tokens = 0
            total_output_tokens = 0
            finish_reasons = []

            for i in range(params.max_iterations):
                arguments = {
                    "messages": messages,
                    "temperature": params.temperature,
                    "model": model,
                    "max_tokens": params.maxTokens,
                    "stop": params.stopSequences,
                    "tools": tools,
                }

                # Add user parameter if present in params or config
                user = params.user or getattr(self.context.config.azure, "user", None)
                if user:
                    arguments["user"] = user

                if params.metadata:
                    arguments = {**arguments, **params.metadata}

                self.logger.debug("Completion request arguments:", data=arguments)
                self._log_chat_progress(chat_turn=(len(messages) + 1) // 2, model=model)

                request = RequestCompletionRequest(
                    config=self.context.config.azure,
                    payload=arguments,
                )
                self._annotate_span_for_completion_request(span, request, i)

                response = await self.executor.execute(
                    AzureCompletionTasks.request_completion_task,
                    request,
                )

                if isinstance(response, BaseException):
                    self.logger.error(f"Error: {response}")
                    span.record_exception(response)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    break

                self.logger.debug(f"{model} response:", data=response)

                self._annotate_span_for_completion_response(span, response, i)

                # Per-iteration token counts
                iteration_input = response.usage["prompt_tokens"]
                iteration_output = response.usage["completion_tokens"]

                total_input_tokens += iteration_input
                total_output_tokens += iteration_output
                finish_reasons.append(response.choices[0].finish_reason)

                # Incremental token tracking inside loop so watchers update during long runs
                if self.context.token_counter:
                    await self.context.token_counter.record_usage(
                        input_tokens=iteration_input,
                        output_tokens=iteration_output,
                        model_name=model,
                        provider=self.provider,
                    )

                message = response.choices[0].message
                responses.append(message)
                assistant_message = self.convert_message_to_message_param(message)
                messages.append(assistant_message)

                if (
                    response.choices[0].finish_reason
                    == CompletionsFinishReason.TOOL_CALLS
                ):
                    if (
                        response.choices[0].message.tool_calls is not None
                        and len(response.choices[0].message.tool_calls) > 0
                    ):
                        tool_tasks = [
                            self.execute_tool_call(tool_call)
                            for tool_call in response.choices[0].message.tool_calls
                        ]

                        tool_results = await self.executor.execute_many(tool_tasks)

                        self.logger.debug(
                            f"Iteration {i}: Tool call results: {str(tool_results) if tool_results else 'None'}"
                        )

                        for result in tool_results:
                            if isinstance(result, BaseException):
                                self.logger.error(
                                    f"Warning: Unexpected error during tool execution: {result}. Continuing..."
                                )
                                span.record_exception(result)
                                continue
                            elif isinstance(result, ToolMessage):
                                messages.append(result)
                                responses.append(result)
                else:
                    self.logger.debug(
                        f"Iteration {i}: Stopping because finish_reason is '{response.choices[0].finish_reason}'"
                    )
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
        The default implementation uses Azure OpenAI 4o-mini as the LLM.
        Override this method to use a different LLM.
        """
        responses = await self.generate(
            message=message,
            request_params=request_params,
        )

        final_text: list[str] = []

        for response in responses:
            if response.content:
                if response.role == "tool":
                    # TODO: Identify tool name
                    final_text.append(f"[Tool result: {response.content}]")
                else:
                    final_text.append(response.content)
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    if tool_call.function.arguments:
                        final_text.append(
                            f"[Calling tool {tool_call.function.name} with args {tool_call.function.arguments}]"
                        )

        return "\n".join(final_text)

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        json_schema = response_model.model_json_schema()

        request_params = request_params or RequestParams()
        metadata = request_params.metadata or {}
        metadata["response_format"] = JsonSchemaFormat(
            name=response_model.__name__,
            description=response_model.__doc__,
            schema=json_schema,
            strict=request_params.strict,
        )
        request_params.metadata = metadata

        response = await self.generate(message=message, request_params=request_params)
        json_data = json.loads(response[-1].content)

        structured_response = response_model.model_validate(json_data)
        return structured_response

    @classmethod
    def convert_message_to_message_param(
        cls, message: ResponseMessage
    ) -> AssistantMessage:
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        assistant_message = AssistantMessage(
            content=message.content,
            tool_calls=message.tool_calls,
        )
        return assistant_message

    async def execute_tool_call(
        self,
        tool_call: ChatCompletionsToolCall,
    ) -> ToolMessage | None:
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
                tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            return ToolMessage(
                tool_call_id=tool_call_id,
                content=f"Invalid JSON provided in tool call arguments for '{tool_name}'. Failed to load JSON: {str(e)}",
            )
        except Exception as e:
            return ToolMessage(
                tool_call_id=tool_call_id,
                content=f"Error executing tool '{tool_name}': {str(e)}",
            )

        try:
            tool_call_request = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name=tool_name, arguments=tool_args),
            )

            result = await self.call_tool(
                request=tool_call_request, tool_call_id=tool_call_id
            )

            if result.content:
                return ToolMessage(
                    tool_call_id=tool_call_id,
                    content=mcp_content_to_azure_content(result.content),
                )

            return None
        except Exception as e:
            return ToolMessage(
                tool_call_id=tool_call_id,
                content=f"Error executing tool '{tool_name}': {str(e)}",
            )

    def message_param_str(self, message: MessageParam) -> str:
        """Convert an input message to a string representation."""
        if message.content:
            if isinstance(message.content, str):
                return message.content

            content: list[str] = []
            for c in message.content:
                if isinstance(c, TextContentItem):
                    content.append(c.text)
                elif isinstance(c, ImageContentItem):
                    content.append(f"Image url: {c.image_url.url}")
                elif isinstance(c, AudioContentItem):
                    content.append(f"{c.input_audio.format}: {c.input_audio.data}")
                else:
                    content.append(str(c))
            return "\n".join(content)
        else:
            return str(message)

    def message_str(self, message: ResponseMessage, content_only: bool = False) -> str:
        """Convert an output message to a string representation."""
        if message.content:
            return message.content
        elif content_only:
            # If content_only is True, return empty string if no content
            return ""

        return str(message)

    def _annotate_span_for_completion_request(
        self, span: trace.Span, request: RequestCompletionRequest, turn: int
    ) -> None:
        """Annotate the span with the completion request as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.request.turn": turn,
            "config.endpoint": request.config.endpoint,
        }

        # TODO: rholinshead - serialize RequestCompletionRequest dict

        # Event name is based on the latest message role
        event_name = f"completion.request.{turn}"
        latest_message_role = request.payload.get("messages", [{}])[-1].get("role")

        if latest_message_role:
            event_name = f"gen_ai.{latest_message_role}.message"

        span.add_event(event_name, event_data)

    def _annotate_span_for_completion_response(
        self, span: trace.Span, response: ResponseMessage, turn: int
    ) -> None:
        """Annotate the span with the completion response as an event."""
        if not self.context.tracing_enabled:
            return

        event_data = {
            "completion.response.turn": turn,
        }

        event_data.update(
            self.extract_response_message_attributes_for_tracing(response)
        )

        # Event name is based on the first choice for now
        event_name = f"completion.response.{turn}"
        if response.choices and len(response.choices) > 0:
            latest_message_role = response.choices[0].message.role
            event_name = f"gen_ai.{latest_message_role}.message"

        span.add_event(event_name, event_data)

    def _extract_message_param_attributes_for_tracing(
        self, message_param: MessageParam, prefix: str = "message"
    ) -> dict[str, Any]:
        """Return a flat dict of span attributes for a given MessageParam."""
        attrs = {}
        # TODO: rholinshead - serialize MessageParam dict
        return attrs

    def extract_response_message_attributes_for_tracing(
        self, message: ResponseMessage, prefix: str | None = None
    ) -> dict[str, Any]:
        """Return a flat dict of span attributes for a given ResponseMessage."""
        attrs = {}
        # TODO: rholinshead - serialize ResponseMessage dict
        return attrs


class AzureCompletionTasks:
    @staticmethod
    @workflow_task
    async def request_completion_task(
        request: RequestCompletionRequest,
    ) -> ChatCompletions:
        """
        Request a completion from Azure's API.
        """
        if request.config.api_key:
            azure_client = ChatCompletionsClient(
                endpoint=request.config.endpoint,
                credential=AzureKeyCredential(request.config.api_key),
                **request.config.model_dump(exclude={"endpoint", "credential"}),
            )
        else:
            azure_client = ChatCompletionsClient(
                endpoint=request.config.endpoint,
                credential=DefaultAzureCredential(),
                credential_scopes=request.config.credential_scopes,
                **request.config.model_dump(
                    exclude={"endpoint", "credential", "credential_scopes"}
                ),
            )

        payload = request.payload.copy()
        loop = asyncio.get_running_loop()

        try:
            response = await loop.run_in_executor(
                None, functools.partial(azure_client.complete, **payload)
            )
        except HttpResponseError as e:
            logger = get_logger(__name__)

            if e.status_code != 400:
                logger.error(f"Azure API call failed: {e}")
                raise

            logger.warning(
                f"Initial Azure API call failed: {e}. Retrying with fallback parameters."
            )

            # Create a new payload with fallback values for commonly problematic parameters
            fallback_payload = {**payload, "max_tokens": None, "temperature": 1}

            try:
                response = await loop.run_in_executor(
                    None, functools.partial(azure_client.complete, **fallback_payload)
                )
            except Exception as retry_error:
                # If retry also fails, raise a more informative error
                raise RuntimeError(
                    f"Azure API call failed even with fallback parameters. "
                    f"Original error: {e}. Retry error: {retry_error}"
                ) from retry_error
        return response


class MCPAzureTypeConverter(ProviderToMCPConverter[MessageParam, ResponseMessage]):
    """
    Convert between Azure and MCP types.
    """

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> ResponseMessage:
        if result.role != "assistant":
            raise ValueError(
                f"Expected role to be 'assistant' but got '{result.role}' instead."
            )
        if isinstance(result.content, TextContent):
            return AssistantMessage(content=result.content.text)
        else:
            return AssistantMessage(
                content=f"{result.content.mimeType}:{result.content.data}"
            )

    @classmethod
    def to_mcp_message_result(cls, result: ResponseMessage) -> MCPMessageResult:
        return MCPMessageResult(
            role=result.role,
            content=TextContent(type="text", text=result.content),
            model="",
            stopReason=None,
        )

    @classmethod
    def from_mcp_message_param(cls, param: MCPMessageParam) -> MessageParam:
        if param.role == "assistant":
            extras = param.model_dump(exclude={"role", "content"})
            return AssistantMessage(
                content=mcp_content_to_azure_content([param.content]),
                **extras,
            )
        elif param.role == "user":
            extras = param.model_dump(exclude={"role", "content"})
            return UserMessage(
                content=mcp_content_to_azure_content([param.content], str_only=False),
                **extras,
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, MCP only supports 'assistant' and 'user'"
            )

    @classmethod
    def to_mcp_message_param(cls, param: MessageParam) -> MCPMessageParam:
        contents = azure_content_to_mcp_content(param.content)

        # TODO: saqadri - the mcp_content can have multiple elements
        # while sampling message content has a single content element
        # Right now we error out if there are > 1 elements in mcp_content
        # We need to handle this case properly going forward
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported"
            )
        elif len(contents) == 0:
            raise ValueError("No content elements in a message")

        mcp_content: TextContent | ImageContent | EmbeddedResource = contents[0]

        if param.role == ChatRole.ASSISTANT:
            return MCPMessageParam(
                role="assistant",
                content=mcp_content,
                **typed_dict_extras(param, ["role", "content"]),
            )
        elif param.role == ChatRole.USER:
            return MCPMessageParam(
                role="user",
                content=mcp_content,
                **typed_dict_extras(param, ["role", "content"]),
            )
        elif param.role == ChatRole.TOOL:
            raise NotImplementedError(
                "Tool messages are not supported in SamplingMessage yet"
            )
        elif param.role == ChatRole.SYSTEM:
            raise NotImplementedError(
                "System messages are not supported in SamplingMessage yet"
            )
        elif param.role == ChatRole.DEVELOPER:
            raise NotImplementedError(
                "Developer messages are not supported in SamplingMessage yet"
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, Azure only supports 'assistant', 'user', 'tool', 'system', 'developer'"
            )


def mcp_content_to_azure_content(
    content: list[TextContent | ImageContent | EmbeddedResource], str_only: bool = True
) -> str | list[ContentItem]:
    """
    Convert a list of MCP content types (TextContent, ImageContent, EmbeddedResource)
    into Azure-compatible content types or a string.

    Args:
        content (list[TextContent | ImageContent | EmbeddedResource]):
            The list of MCP content objects to convert.
        str_only (bool, optional):
            If True, returns a string representation of the content.
            If False, returns a list of Azure ContentItem objects.
            Defaults to True.

    Returns:
        str | list[ContentItem]:
            A newline-joined string if str_only is True, otherwise a list of ContentItem.
    """
    if str_only:
        text_parts: list[str] = []
        for c in content:
            if isinstance(c, TextContent):
                text_parts.append(c.text)
            elif isinstance(c, ImageContent):
                text_parts.append(f"{c.mimeType}:{c.data}")
            elif isinstance(c, EmbeddedResource):
                if isinstance(c.resource, TextResourceContents):
                    text_parts.append(c.resource.text)
                else:
                    text_parts.append(f"{c.resource.mimeType}:{c.resource.blob}")
        return "\n".join(text_parts)

    # Not str_only - build list of ContentItem
    azure_content: list[ContentItem] = []
    for c in content:
        if isinstance(c, TextContent):
            azure_content.append(TextContentItem(text=c.text))
        elif isinstance(c, ImageContent):
            data_url = f"data:{c.mimeType};base64,{c.data}"
            azure_content.append(ImageContentItem(image_url=ImageUrl(url=data_url)))
        elif isinstance(c, EmbeddedResource):
            if isinstance(c.resource, TextResourceContents):
                azure_content.append(TextContentItem(text=c.resource.text))
            else:
                data_url = f"data:{c.resource.mimeType};base64,{c.resource.blob}"
                azure_content.append(ImageContentItem(image_url=ImageUrl(url=data_url)))
    return azure_content


def azure_content_to_mcp_content(
    content: str | list[ContentItem] | None,
) -> Iterable[TextContent | ImageContent | EmbeddedResource]:
    mcp_content: Iterable[TextContent | ImageContent | EmbeddedResource] = []
    if content is None:
        return mcp_content
    elif isinstance(content, str):
        return [TextContent(type="text", text=content)]

    for item in content:
        if isinstance(item, TextContentItem):
            mcp_content.append(TextContent(type="text", text=item.text))
        elif isinstance(item, ImageContentItem):
            mime_type, base64_data = image_url_to_mime_and_base64(item.image_url)
            mcp_content.append(
                ImageContent(
                    type="image",
                    mimeType=mime_type,
                    data=base64_data,
                )
            )
        elif isinstance(item, AudioContentItem):
            raise NotImplementedError("Audio content conversion not implemented")

    return mcp_content


def image_url_to_mime_and_base64(image_url: ImageUrl) -> tuple[str, str]:
    """
    Extract mime type and base64 data from ImageUrl
    """
    import re

    url = image_url.url

    match = re.match(r"data:(image/\w+);base64,(.*)", url)
    if not match:
        raise ValueError(f"Invalid image data URI: {url[:30]}...")
    mime_type, base64_data = match.groups()
    return mime_type, base64_data
