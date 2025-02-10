from abc import abstractmethod

from typing import Generic, List, Optional, Protocol, Type, TypeVar, TYPE_CHECKING

from pydantic import Field

from mcp.types import (
    CallToolRequest,
    CallToolResult,
    CreateMessageRequestParams,
    CreateMessageResult,
    SamplingMessage,
    TextContent,
)

from mcp_agent.context_dependent import ContextDependent
from mcp_agent.mcp.mcp_aggregator import MCPAggregator
from mcp_agent.workflows.llm.llm_selector import ModelSelector

if TYPE_CHECKING:
    from mcp_agent.agents.agent import Agent
    from mcp_agent.context import Context

MessageParamT = TypeVar("MessageParamT")
"""A type representing an input message to an LLM."""

MessageT = TypeVar("MessageT")
"""A type representing an output message from an LLM."""

ModelT = TypeVar("ModelT")
"""A type representing a structured output message from an LLM."""

# TODO: saqadri - SamplingMessage is fairly limiting - consider extending
MCPMessageParam = SamplingMessage
MCPMessageResult = CreateMessageResult


class Memory(Protocol, Generic[MessageParamT]):
    """
    Simple memory management for storing past interactions in-memory.
    """

    # TODO: saqadri - add checkpointing and other advanced memory capabilities

    def __init__(self): ...

    def extend(self, messages: List[MessageParamT]) -> None: ...

    def set(self, messages: List[MessageParamT]) -> None: ...

    def append(self, message: MessageParamT) -> None: ...

    def get(self) -> List[MessageParamT]: ...

    def clear(self) -> None: ...


class SimpleMemory(Memory, Generic[MessageParamT]):
    """
    Simple memory management for storing past interactions in-memory.
    """

    def __init__(self):
        self.history: List[MessageParamT] = []

    def extend(self, messages: List[MessageParamT]):
        self.history.extend(messages)

    def set(self, messages: List[MessageParamT]):
        self.history = messages.copy()

    def append(self, message: MessageParamT):
        self.history.append(message)

    def get(self) -> List[MessageParamT]:
        return self.history

    def clear(self):
        self.history = []


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

    parallel_tool_calls: bool = True
    """
    Whether to allow multiple tool calls per iteration.
    Also known as multi-step tool use.
    """


class AugmentedLLMProtocol(Protocol, Generic[MessageParamT, MessageT]):
    """Protocol defining the interface for augmented LLMs"""

    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Request an LLM generation, which may run multiple iterations, and return the result"""

    async def generate_str(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""

    async def generate_structured(
        self,
        message: str | MessageParamT | List[MessageParamT],
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
        self.aggregator = (
            agent if agent is not None else MCPAggregator(server_names or [])
        )
        self.name = name or (agent.name if agent else None)
        self.instruction = instruction or (
            agent.instruction if agent and isinstance(agent.instruction, str) else None
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

    @abstractmethod
    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Request an LLM generation, which may run multiple iterations, and return the result"""

    @abstractmethod
    async def generate_str(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""

    @abstractmethod
    async def generate_structured(
        self,
        message: str | MessageParamT | List[MessageParamT],
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
        model_preferences = self.model_preferences
        if request_params is not None:
            model_preferences = request_params.modelPreferences or model_preferences
            model = request_params.model
            if model:
                return model

        if not self.model_selector:
            self.model_selector = ModelSelector()

        model_info = self.model_selector.select_best_model(
            model_preferences=model_preferences, provider=self.provider
        )

        return model_info.name

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

        try:
            preprocess = await self.pre_tool_call(
                tool_call_id=tool_call_id,
                request=request,
            )

            if isinstance(preprocess, bool):
                if not preprocess:
                    return CallToolResult(
                        isError=True,
                        content=[
                            TextContent(
                                text=f"Error: Tool '{request.params.name}' was not allowed to run."
                            )
                        ],
                    )
            else:
                request = preprocess

            tool_name = request.params.name
            tool_args = request.params.arguments
            result = await self.aggregator.call_tool(tool_name, tool_args)

            postprocess = await self.post_tool_call(
                tool_call_id=tool_call_id, request=request, result=result
            )

            if isinstance(postprocess, CallToolResult):
                result = postprocess

            return result
        except Exception as e:
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Error executing tool '{request.params.name}': {str(e)}",
                    )
                ],
            )

    def message_param_str(self, message: MessageParamT) -> str:
        """Convert an input message to a string representation."""
        return str(message)

    def message_str(self, message: MessageT) -> str:
        """Convert an output message to a string representation."""
        return str(message)

    def _log_chat_progress(
        self, chat_turn: Optional[int] = None, model: Optional[str] = None
    ):
        """Log a chat progress event"""
        data = {
            "progress_action": "Chatting",
            "model": model,
            "agent_name": self.name,
            "chat_turn": chat_turn if chat_turn is not None else None,
        }
        self.logger.debug("Chat in progress", data=data)

    def _log_chat_finished(self, model: Optional[str] = None):
        """Log a chat finished event"""
        data = {"progress_action": "Finished", "model": model, "agent_name": self.name}
        self.logger.debug("Chat finished", data=data)
