from abc import abstractmethod

from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Set,
    Type,
    TypeVar,
    Union,
    TYPE_CHECKING,
)

from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from mcp.types import (
    CallToolRequest,
    CallToolResult,
    CreateMessageRequestParams,
    CreateMessageResult,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    SamplingMessage,
    TextContent,
    PromptMessage,
)

from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.tracing.semconv import (
    GEN_AI_AGENT_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_STOP_SEQUENCES,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_NAME,
)
from mcp_agent.tracing.telemetry import (
    get_tracer,
    record_attribute,
    record_attributes,
)
from mcp_agent.workflows.llm.llm_selector import ModelSelector

if TYPE_CHECKING:
    from mcp_agent.core.context import Context
    from mcp_agent.logging.logger import Logger
    from mcp_agent.agents.agent import Agent


MessageParamT = TypeVar("MessageParamT")
"""A type representing an input message to an LLM."""

MessageT = TypeVar("MessageT")
"""A type representing an output message from an LLM."""

ModelT = TypeVar("ModelT")
"""A type representing a structured output message from an LLM."""

# TODO: saqadri - SamplingMessage is fairly limiting - consider extending
MCPMessageParam = SamplingMessage
MCPMessageResult = CreateMessageResult

# Accepted message types for the AugmentedLLM generation methods.
Message = Union[str, MessageParamT, PromptMessage]
MessageTypes = Union[Message, List[Message]]


class Memory(BaseModel, Generic[MessageParamT]):
    """
    Simple memory management for storing past interactions in-memory.
    """

    # Pydantic settings common to all memories
    model_config = ConfigDict(
        arbitrary_types_allowed=True,  # lets MessageParamT be anything (e.g. a pydantic model)
        extra="allow",  # fail fast on unexpected attributes
    )

    def extend(self, messages: List[MessageParamT]) -> None:  # noqa: D401
        raise NotImplementedError

    def set(self, messages: List[MessageParamT]) -> None:
        raise NotImplementedError

    def append(self, message: MessageParamT) -> None:
        raise NotImplementedError

    def get(self) -> List[MessageParamT]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class SimpleMemory(Memory[MessageParamT]):
    """
    In-memory implementation that just keeps an ordered list of messages.
    """

    history: List[MessageParamT] = Field(default_factory=list)

    def extend(self, messages: List[MessageParamT]):
        self.history.extend(messages)

    def set(self, messages: List[MessageParamT]):
        self.history = messages.copy()

    def append(self, message: MessageParamT):
        self.history.append(message)

    def get(self) -> List[MessageParamT]:
        return list(self.history)

    def clear(self):
        self.history.clear()


class RequestParams(CreateMessageRequestParams):
    """
    Parameters to configure the AugmentedLLM 'generate' requests.
    """

    messages: None = Field(exclude=True, default=None)
    """
    Ignored. 'messages' are removed from CreateMessageRequestParams 
    to avoid confusion with the 'message' parameter on 'generate' method.
    """

    maxTokens: int = 2048
    """The maximum number of tokens to sample, as requested by the server."""

    model: str | None = None
    """
    The model to use for the LLM generation.
    If specified, this overrides the 'modelPreferences' selection criteria.
    """

    use_history: bool = True
    """
    Include the message history in the generate request.
    """

    max_iterations: int = 10
    """
    The maximum number of iterations to run the LLM for.
    """

    parallel_tool_calls: bool = False
    """
    Whether to allow multiple tool calls per iteration.
    Also known as multi-step tool use.
    """

    temperature: float = 0.7
    """
    The likelihood of the model selecting higher-probability options while generating a response.
    """

    user: str | None = None
    """
    The user to use for the LLM generation.
    This is used to stably identify the user in the LLM provider's logs.
    """

    strict: bool = False
    """
    Whether models that support strict mode should strictly enforce the response schema.
    """

    tool_filter: Dict[str, Set[str]] | None = None
    """
    Mapping of server names to sets of allowed tool names for this request.
    If specified, only these tools will be exposed to the LLM for each server.
    This overrides the server-level allowed_tools configuration.

    Special reserved keys:
        - "*": Wildcard filter for servers without explicit filters
        - "non_namespaced_tools": Filter for non-namespaced tools (function tools, human input)

    Examples:
        - {"server1": {"tool1", "tool2"}} - Allow specific tools from server1
        - {"*": {"tool1"}} - Allow tool1 from all servers without explicit filters
        - {"non_namespaced_tools": {"human_input", "func1"}} - Allow specific non-namespaced tools
        - {} - No tools allowed from any server
        - None - No filtering applied (default behavior)

    Tool names should match exactly as they appear in the server's tool list.
    """


class AugmentedLLMProtocol(Protocol, Generic[MessageParamT, MessageT]):
    """Protocol defining the interface for augmented LLMs"""

    async def generate(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Request an LLM generation, which may run multiple iterations, and return the result"""

    async def generate_str(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""

    async def generate_structured(
        self,
        message: MessageTypes,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Request a structured LLM generation and return the result as a Pydantic model."""


class ProviderToMCPConverter(Protocol, Generic[MessageParamT, MessageT]):
    """Conversions between LLM provider and MCP types"""

    @classmethod
    def to_mcp_message_result(cls, result: MessageT) -> MCPMessageResult:
        """Convert an LLM response to an MCP message result type."""

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> MessageT:
        """Convert an MCP message result to an LLM response type."""

    @classmethod
    def to_mcp_message_param(cls, param: MessageParamT) -> MCPMessageParam:
        """Convert an LLM input to an MCP message (SamplingMessage) type."""

    @classmethod
    def from_mcp_message_param(cls, param: MCPMessageParam) -> MessageParamT:
        """Convert an MCP message (SamplingMessage) to an LLM input type."""

    @classmethod
    def from_mcp_tool_result(
        cls, result: CallToolResult, tool_use_id: str
    ) -> MessageParamT:
        """Convert an MCP tool result to an LLM input type"""


class AugmentedLLM(ContextDependent, AugmentedLLMProtocol[MessageParamT, MessageT]):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    Our current models can actively use these capabilities—generating their own search queries,
    selecting appropriate tools, and determining what information to retain.
    """

    # TODO: saqadri - add streaming support (e.g. generate_stream)
    # TODO: saqadri - consider adding middleware patterns for pre/post processing of messages, for now we have pre/post_tool_call

    provider: str | None = None
    logger: Union["Logger", None] = None
    # Suggested node type for token tracking for base LLMs
    token_node_type: str = "llm"

    def __init__(
        self,
        agent: Optional["Agent"] = None,
        server_names: List[str] | None = None,
        instruction: str | None = None,
        name: str | None = None,
        default_request_params: RequestParams | None = None,
        type_converter: Type[ProviderToMCPConverter[MessageParamT, MessageT]] = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        """
        Initialize the LLM with a list of server names and an instruction.
        If a name is provided, it will be used to identify the LLM.
        If an agent is provided, all other properties are optional
        """
        super().__init__(context=context, **kwargs)
        self.executor = self.context.executor
        self.name = self._gen_name(name or (agent.name if agent else None), prefix=None)
        self.instruction = instruction or (agent.instruction if agent else None)

        if not self.name:
            raise ValueError(
                "An AugmentedLLM must have a name or be provided with an agent that has a name"
            )

        if agent:
            self.agent = agent
        else:
            # Import here to avoid circular import
            from mcp_agent.agents.agent import Agent

            self.agent = Agent(
                name=self.name,
                # Only pass instruction if it's not None
                **(
                    {"instruction": self.instruction}
                    if self.instruction is not None
                    else {}
                ),
                server_names=server_names or [],
                llm=self,
            )

        self.history: Memory[MessageParamT] = SimpleMemory[MessageParamT]()
        self.default_request_params = default_request_params
        self.model_preferences = (
            self.default_request_params.modelPreferences
            if self.default_request_params
            else None
        )

        self.model_selector = self.context.model_selector
        self.type_converter = type_converter

    async def __aenter__(self):
        if self.agent:
            await self.agent.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.agent:
            await self.agent.__aexit__(exc_type, exc_val, exc_tb)

    @abstractmethod
    async def generate(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Request an LLM generation, which may run multiple iterations, and return the result"""

    @abstractmethod
    async def generate_str(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""

    @abstractmethod
    async def generate_structured(
        self,
        message: MessageTypes,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Request a structured LLM generation and return the result as a Pydantic model."""

    async def select_model(
        self, request_params: RequestParams | None = None
    ) -> str | None:
        """
        Select an LLM based on the request parameters.
        If a model is specified in the request, it will override the model selection criteria.
        """
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.select_model"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            model_preferences = self.model_preferences
            if request_params is not None:
                model_preferences = request_params.modelPreferences or model_preferences
                model = request_params.model
                if model:
                    # Take user-specified model ID exactly as provided (no normalization)
                    span.set_attribute("request_params.model", model)
                    span.set_attribute("model", model)
                    return model

            if not self.model_selector:
                self.model_selector = ModelSelector(context=self.context)

            try:
                model_info = self.model_selector.select_best_model(
                    model_preferences=model_preferences, provider=self.provider
                )

                # Model names from benchmarks are already normalized; return as-is
                selected = model_info.name
                span.set_attribute("model", selected)
                return selected
            except ValueError as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                model = (
                    self.default_request_params.model
                    if self.default_request_params
                    else None
                )
                if model:
                    span.set_attribute("model", model)
                return model

    def get_request_params(
        self,
        request_params: RequestParams | None = None,
        default: RequestParams | None = None,
    ) -> RequestParams:
        """
        Get request parameters with merged-in defaults and overrides.
        Args:
            request_params: The request parameters to use as overrides.
            default: The default request parameters to use as the base.
                If unspecified, self.default_request_params will be used.
        """
        # Start with the defaults
        default_request_params = default or self.default_request_params

        params = default_request_params.model_dump() if default_request_params else {}
        # If user provides overrides, update the defaults
        if request_params:
            params.update(request_params.model_dump(exclude_unset=True))

        # Create a new RequestParams object with the updated values
        return RequestParams(**params)

    def to_mcp_message_result(self, result: MessageT) -> MCPMessageResult:
        """Convert an LLM response to an MCP message result type."""
        return self.type_converter.to_mcp_message_result(result)

    def from_mcp_message_result(self, result: MCPMessageResult) -> MessageT:
        """Convert an MCP message result to an LLM response type."""
        return self.type_converter.from_mcp_message_result(result)

    def to_mcp_message_param(self, param: MessageParamT) -> MCPMessageParam:
        """Convert an LLM input to an MCP message (SamplingMessage) type."""
        return self.type_converter.to_mcp_message_param(param)

    def from_mcp_message_param(self, param: MCPMessageParam) -> MessageParamT:
        """Convert an MCP message (SamplingMessage) to an LLM input type."""
        return self.type_converter.from_mcp_message_param(param)

    def from_mcp_tool_result(
        self, result: CallToolResult, tool_use_id: str
    ) -> MessageParamT:
        """Convert an MCP tool result to an LLM input type"""
        return self.type_converter.from_mcp_tool_result(result, tool_use_id)

    @classmethod
    def convert_message_to_message_param(
        cls, message: MessageT, **kwargs
    ) -> MessageParamT:
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        # Many LLM implementations will allow the same type for input and output messages
        return message

    async def get_last_message(self) -> MessageParamT | None:
        """
        Return the last message generated by the LLM or None if history is empty.
        This is useful for prompt chaining workflows where the last message from one LLM is used as input to another.
        """
        history = self.history.get()
        return history[-1] if history else None

    async def get_last_message_str(self) -> str | None:
        """Return the string representation of the last message generated by the LLM or None if history is empty."""
        last_message = await self.get_last_message()
        return self.message_param_str(last_message) if last_message else None

    # region Agent / MCP convenience methods

    async def pre_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest
    ) -> CallToolRequest | bool:
        """Called before a tool is executed. Return False to prevent execution."""
        return request

    async def post_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest, result: CallToolResult
    ) -> CallToolResult:
        """Called after a tool execution. Can modify the result before it's returned."""
        return result

    async def call_tool(
        self,
        request: CallToolRequest,
        tool_call_id: str | None = None,
    ) -> CallToolResult:
        """Call a tool with the given parameters and optional ID"""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.call_tool"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
                if tool_call_id:
                    span.set_attribute(GEN_AI_TOOL_CALL_ID, tool_call_id)
                    span.set_attribute("request.method", request.method)

                span.set_attribute("request.params.name", request.params.name)
                if request.params.arguments:
                    record_attributes(
                        span, request.params.arguments, "request.params.arguments"
                    )

            try:
                preprocess = await self.pre_tool_call(
                    tool_call_id=tool_call_id,
                    request=request,
                )

                if isinstance(preprocess, bool):
                    if not preprocess:
                        span.set_attribute("preprocess", False)
                        span.set_status(trace.Status(trace.StatusCode.ERROR))

                        res = CallToolResult(
                            isError=True,
                            content=[
                                TextContent(
                                    text=f"Error: Tool '{request.params.name}' was not allowed to run."
                                )
                            ],
                        )
                        span.record_exception(Exception(res.content[0].text))
                        return res
                else:
                    request = preprocess

                tool_name = request.params.name
                tool_args = request.params.arguments

                span.set_attribute(f"processed.request.{GEN_AI_TOOL_NAME}", tool_name)
                if self.context.tracing_enabled and tool_args:
                    record_attributes(span, tool_args, "processed.request.tool_args")

                result = await self.agent.call_tool(tool_name, tool_args)
                self._annotate_span_for_call_tool_result(span, result)

                postprocess = await self.post_tool_call(
                    tool_call_id=tool_call_id, request=request, result=result
                )

                if isinstance(postprocess, CallToolResult):
                    result = postprocess
                    self._annotate_span_for_call_tool_result(
                        span, result, processed=True
                    )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                return CallToolResult(
                    isError=True,
                    content=[
                        TextContent(
                            type="text",
                            text=f"Error executing tool '{request.params.name}': {str(e)}",
                        )
                    ],
                )

    async def list_tools(
        self,
        server_name: str | None = None,
        tool_filter: Dict[str, Set[str]] | None = None,
    ) -> ListToolsResult:
        """Call the underlying agent's list_tools method for a given server."""
        return await self.agent.list_tools(
            server_name=server_name, tool_filter=tool_filter
        )

    async def list_resources(
        self, server_name: str | None = None
    ) -> ListResourcesResult:
        """Call the underlying agent's list_resources method for a given server."""
        return await self.agent.list_resources(server_name=server_name)

    async def read_resource(
        self, uri: str, server_name: str | None = None
    ) -> ReadResourceResult:
        """Call the underlying agent's read_resource method for a given server."""
        return await self.agent.read_resource(uri=uri, server_name=server_name)

    async def list_prompts(self, server_name: str | None = None) -> ListPromptsResult:
        """Call the underlying agent's list_prompts method for a given server."""
        return await self.agent.list_prompts(server_name=server_name)

    async def get_prompt(
        self, name: str, server_name: str | None = None
    ) -> GetPromptResult:
        """Call the underlying agent's get_prompt method for a given server."""
        return await self.agent.get_prompt(name=name, server_name=server_name)

    async def close(self):
        """Close underlying agent connections."""
        await self.agent.close()

    # endregion

    def message_param_str(self, message: MessageParamT) -> str:
        """Convert an input message to a string representation."""
        return str(message)

    def message_str(self, message: MessageT, content_only: bool = False) -> str:
        """Convert an output message to a string representation."""
        return str(message)

    def _log_chat_progress(
        self, chat_turn: Optional[int] = None, model: str | None = None
    ):
        """Log a chat progress event"""
        data = {
            "progress_action": "Chatting",
            "model": model,
            "agent_name": self.name,
            "chat_turn": chat_turn if chat_turn is not None else None,
        }
        self.logger.debug("Chat in progress", data=data)

    def _log_chat_finished(self, model: str | None = None):
        """Log a chat finished event"""
        data = {"progress_action": "Finished", "model": model, "agent_name": self.name}
        self.logger.debug("Chat finished", data=data)

    @staticmethod
    def annotate_span_with_request_params(
        span: trace.Span, request_params: RequestParams
    ):
        """Annotate the span with request parameters"""
        # Handle case where request_params might not be a proper RequestParams object
        if hasattr(request_params, "maxTokens"):
            span.set_attribute(GEN_AI_REQUEST_MAX_TOKENS, request_params.maxTokens)
        if hasattr(request_params, "max_iterations"):
            span.set_attribute(
                "request_params.max_iterations", request_params.max_iterations
            )
        if hasattr(request_params, "temperature"):
            span.set_attribute(GEN_AI_REQUEST_TEMPERATURE, request_params.temperature)
        if hasattr(request_params, "use_history"):
            span.set_attribute("request_params.use_history", request_params.use_history)
        if hasattr(request_params, "parallel_tool_calls"):
            span.set_attribute(
                "request_params.parallel_tool_calls", request_params.parallel_tool_calls
            )
        if hasattr(request_params, "model") and request_params.model:
            span.set_attribute(GEN_AI_REQUEST_MODEL, request_params.model)
        if (
            hasattr(request_params, "modelPreferences")
            and request_params.modelPreferences
        ):
            for attr, value in request_params.modelPreferences.model_dump(
                exclude_unset=True
            ).items():
                if attr == "hints" and value is not None:
                    span.set_attribute(
                        "request_params.modelPreferences.hints",
                        [hint.name for hint in value],
                    )
                else:
                    record_attribute(
                        span, f"request_params.modelPreferences.{attr}", value
                    )
        if hasattr(request_params, "systemPrompt") and request_params.systemPrompt:
            span.set_attribute(
                "request_params.systemPrompt", request_params.systemPrompt
            )
        if hasattr(request_params, "includeContext") and request_params.includeContext:
            span.set_attribute(
                "request_params.includeContext",
                request_params.includeContext,
            )
        if hasattr(request_params, "stopSequences") and request_params.stopSequences:
            span.set_attribute(
                GEN_AI_REQUEST_STOP_SEQUENCES,
                request_params.stopSequences,
            )
        if hasattr(request_params, "metadata") and request_params.metadata:
            record_attributes(span, request_params.metadata, "request_params.metadata")

    def _annotate_span_for_generation_message(
        self,
        span: trace.Span,
        message: str | MessageParamT | List[MessageParamT],
    ) -> None:
        """Annotate the span with the message content."""
        if not self.context.tracing_enabled:
            return

        if isinstance(message, str):
            span.set_attribute("message.content", message)
        elif isinstance(message, list):
            for i, msg in enumerate(message):
                if isinstance(msg, str):
                    span.set_attribute(f"message.{i}", msg)
                else:
                    span.set_attribute(f"message.{i}.content", str(msg))
        else:
            span.set_attribute("message", str(message))

    def _extract_message_param_attributes_for_tracing(
        self, message_param: MessageParamT, prefix: str = "message"
    ) -> dict[str, Any]:
        """
        Return a flat dict of span attributes for a given MessageParamT.
        Override this for the AugmentedLLM subclass MessageParamT type.
        """
        return {}

    def _annotate_span_for_call_tool_result(
        self,
        span: trace.Span,
        result: CallToolResult,
        processed: bool = False,
    ):
        if not self.context.tracing_enabled:
            return

        prefix = "processed.result" if processed else "result"
        span.set_attribute(f"{prefix}.isError", result.isError)
        if result.isError:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            error_message = (
                result.content[0].text
                if len(result.content) > 0 and result.content[0].type == "text"
                else "Error calling tool"
            )
            span.record_exception(Exception(error_message))
        else:
            for idx, content in enumerate(result.content):
                span.set_attribute(f"{prefix}.content.{idx}.type", content.type)
                if content.type == "text":
                    span.set_attribute(
                        f"{prefix}.content.{idx}.text",
                        result.content[idx].text,
                    )

    def extract_response_message_attributes_for_tracing(
        self, message: MessageT, prefix: str | None = None
    ) -> dict[str, Any]:
        """
        Return a flat dict of span attributes for a given MessageT.
        Override this for the AugmentedLLM subclass MessageT type.
        """
        return {}

    def _gen_name(self, name: str | None, prefix: str | None) -> str:
        """
        Generate a name for the LLM based on the provided name or the default prefix.
        """
        if name:
            return name

        if not prefix:
            prefix = self.__class__.__name__

        identifier: str | None = None
        if not self.context or not self.context.executor:
            import uuid

            identifier = str(uuid.uuid4())
        else:
            identifier = str(self.context.executor.uuid())

        return f"{prefix}-{identifier}"

    # region Token tracking

    async def get_token_node(
        self, return_all_matches: bool = False, node_type: str | None = None
    ):
        """Return this LLM's token node(s) from the global counter."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return [] if return_all_matches else None
        counter = self.context.token_counter
        # Prefer explicit node_type, else default to this class's suggested node type
        t = node_type or getattr(self, "token_node_type", None)
        if return_all_matches:
            if t == "llm":
                return await counter.get_llm_node(self.name, return_all_matches=True)
            if t == "agent":
                return await counter.get_agent_node(self.name, return_all_matches=True)
            # Fallback: gather both types
            nodes = await counter.get_llm_node(self.name, return_all_matches=True)
            nodes += await counter.get_agent_node(self.name, return_all_matches=True)
            return nodes
        else:
            if t == "agent":
                node = await counter.get_agent_node(self.name)
                if node:
                    return node
            if t == "llm" or not t:
                node = await counter.get_llm_node(self.name)
                if node:
                    return node
            # Fallback try agent if not found
            return await counter.get_agent_node(self.name)

    async def get_token_usage(self, node_type: str | None = None):
        """Return aggregated token usage for this LLM node (including children)."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return None
        counter = self.context.token_counter
        t = node_type or getattr(self, "token_node_type", None)
        if t == "agent":
            return await counter.get_agent_usage(self.name)
        if t == "llm":
            return await counter.get_node_usage(self.name, "llm")
        # Unknown type: try both
        return await counter.get_node_usage(self.name)

    async def get_token_cost(self, node_type: str | None = None) -> float:
        """Return total cost for this LLM node (including children)."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return 0.0
        counter = self.context.token_counter
        t = node_type or getattr(self, "token_node_type", None)
        if t:
            return await counter.get_node_cost(self.name, t)
        return await counter.get_node_cost(self.name)

    async def watch_tokens(
        self,
        callback,
        *,
        threshold: int | None = None,
        throttle_ms: int | None = None,
        include_subtree: bool = True,
        node_type: str | None = None,
    ) -> str | None:
        """Watch this LLM's token usage. Returns a watch_id or None if not available."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return None
        counter = self.context.token_counter
        t = node_type or getattr(self, "token_node_type", None) or "llm"
        return await counter.watch(
            callback=callback,
            node_name=self.name,
            node_type=t,
            threshold=threshold,
            throttle_ms=throttle_ms,
            include_subtree=include_subtree,
        )

    # endregion
