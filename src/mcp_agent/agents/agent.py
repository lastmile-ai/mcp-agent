import asyncio
import json
import uuid
from typing import Callable, Dict, List, Optional, TypeVar, TYPE_CHECKING, Any

from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from mcp.server.fastmcp.tools import Tool as FastTool
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    Tool,
)

from mcp_agent.core.context import Context
from mcp_agent.mcp.mcp_aggregator import MCPAggregator, NamespacedPrompt, NamespacedTool
from mcp_agent.human_input.types import (
    HumanInputRequest,
    HumanInputResponse,
    HUMAN_INPUT_SIGNAL_NAME,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.logging.tracing import telemetry

if TYPE_CHECKING:
    from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM

    # Define a TypeVar for AugmentedLLM and its subclasses that's only used at type checking time
    LLM = TypeVar("LLM", bound="AugmentedLLM")
else:
    # Define a TypeVar without the bound for runtime
    LLM = TypeVar("LLM")


logger = get_logger(__name__)

HUMAN_INPUT_TOOL_NAME = "__human_input__"


class Agent(BaseModel):
    """
    An Agent is an entity that has access to a set of MCP servers and can interact with them.
    Each agent should have a purpose defined by its instruction.
    """

    name: str
    """Agent name."""

    instruction: str | Callable[[Dict], str] = "You are a helpful agent."
    """
    Instruction for the agent. This can be a string or a callable that takes a dictionary
    and returns a string. The callable can be used to generate dynamic instructions based
    on the context.
    """

    server_names: List[str] = Field(default_factory=list)
    """
    List of MCP server names that the agent can access.
    """

    functions: List[Callable] = Field(default_factory=list)
    """
    List of local functions that the agent can call.
    """

    context: Optional[Context] = None
    """
    The application context that the agent is running in.
    """

    connection_persistence: bool = True
    """
    Whether to persist connections to the MCP servers.
    """

    human_input_callback: Optional[Callable] = None
    """
    Callback function for requesting human input. Must match HumanInputCallback protocol.
    """

    llm: Optional[Any] = None
    """
    The LLM instance that is attached to the agent. This is set in attach_llm method.
    """

    initialized: bool = False
    """
    Whether the agent has been initialized. 
    This is set to True after agent.initialize() is completed.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True, extra="allow"
    )  # allow ContextDependent

    # region Private attributes
    _function_tool_map: Dict[str, FastTool] = PrivateAttr(default_factory=dict)

    # Maps namespaced_tool_name -> namespaced tool info
    _namespaced_tool_map: Dict[str, NamespacedTool] = PrivateAttr(default_factory=dict)
    # Maps server_name -> list of tools
    _server_to_tool_map: Dict[str, List[NamespacedTool]] = PrivateAttr(
        default_factory=dict
    )

    # Maps namespaced_prompt_name -> namespaced prompt info
    _namespaced_prompt_map: Dict[str, NamespacedPrompt] = PrivateAttr(
        default_factory=dict
    )
    # Cache for prompt objects, maps server_name -> list of prompt objects
    _server_to_prompt_map: Dict[str, List[NamespacedPrompt]] = PrivateAttr(
        default_factory=dict
    )

    _agent_tasks: "AgentTasks" = PrivateAttr(default=None)
    _init_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    # endregion

    def model_post_init(self, __context) -> None:
        if self.context is None:
            # Fall back to global context if available
            from mcp_agent.core.context import get_current_context

            self.context = get_current_context()

        # Map function names to tools
        self._function_tool_map = {
            (tool := FastTool.from_function(fn)).name: tool for fn in self.functions
        }

        # Default human_input_callback from context, if absent
        if self.human_input_callback is None:
            ctx_handler = getattr(self.context, "human_input_handler", None)
            if ctx_handler is not None:
                self.human_input_callback = ctx_handler

        self._agent_tasks = AgentTasks(self.context)

    async def attach_llm(
        self, llm_factory: Callable[..., LLM] | None = None, llm: LLM | None = None
    ) -> LLM:
        """
        Create an LLM instance for the agent.

         Args:
            llm_factory: A callable that constructs an AugmentedLLM or its subclass.
                The factory should accept keyword arguments matching the
                AugmentedLLM constructor parameters.
            llm: An instance of AugmentedLLM or its subclass. If provided, this will be used
                instead of creating a new instance.

        Returns:
            An instance of AugmentedLLM or one of its subclasses.
        """
        if llm:
            self.llm = llm
        elif llm_factory:
            self.llm = llm_factory(agent=self)
        else:
            raise ValueError("Either llm_factory or llm must be provided")

        return self.llm

    async def initialize(self, force: bool = False):
        """Initialize the agent."""
        tracer = self.context.tracer or trace.get_tracer("mcp-agent")
        with tracer.start_as_current_span(f"agent.initialize.{self.name}") as span:
            span.set_attribute("name", self.name)
            span.set_attribute("server_names", self.server_names)
            span.set_attribute("connection_persistence", self.connection_persistence)
            span.set_attribute("force", force)

            async with self._init_lock:
                if self.initialized and not force:
                    return

                span.add_event("agent_initialize_start")
                logger.debug(f"Initializing agent {self.name}...")

                executor = self.context.executor

                result: InitAggregatorResponse = await executor.execute(
                    self._agent_tasks.initialize_aggregator_task,
                    InitAggregatorRequest(
                        agent_name=self.name,
                        server_names=self.server_names,
                        connection_persistence=self.connection_persistence,
                        force=force,
                    ),
                )

                if not result.initialized:
                    raise RuntimeError(
                        f"Failed to initialize agent {self.name}. "
                        f"Check the server names and connection persistence settings."
                    )

                # TODO: saqadri - check if a lock is needed here
                self._namespaced_tool_map.clear()
                self._namespaced_tool_map.update(result.namespaced_tool_map)

                self._server_to_tool_map.clear()
                self._server_to_tool_map.update(result.server_to_tool_map)

                self._namespaced_prompt_map.clear()
                self._namespaced_prompt_map.update(result.namespaced_prompt_map)

                self._server_to_prompt_map.clear()
                self._server_to_prompt_map.update(result.server_to_prompt_map)

                self.initialized = result.initialized
                span.add_event("agent_initialize_complete")
                logger.debug(f"Agent {self.name} initialized.")

    async def shutdown(self):
        """
        Shutdown the agent and close all MCP server connections.
        NOTE: This method is called automatically when the agent is used as an async context manager.
        """
        logger.debug(f"Shutting down agent {self.name}...")

        tracer = self.context.tracer or trace.get_tracer("mcp-agent")
        with tracer.start_as_current_span(f"agent.shutdown.{self.name}") as span:
            span.set_attribute("name", self.name)
            span.add_event("agent_shutdown_start")

            executor = self.context.executor
            result: bool = await executor.execute(
                self._agent_tasks.shutdown_aggregator_task,
                self.name,
            )

            if not result:
                raise RuntimeError(
                    f"Failed to shutdown agent {self.name}. "
                    f"Check the server names and connection persistence settings."
                )

            self.initialized = False
            span.add_event("agent_shutdown_complete")
            logger.debug(f"Agent {self.name} shutdown.")

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()

    async def get_capabilities(
        self, server_name: str | None
    ) -> ServerCapabilities | Dict[str, ServerCapabilities]:
        """
        Get the capabilities of a specific server.
        """
        tracer = self.context.tracer or trace.get_tracer("mcp-agent")
        with tracer.start_as_current_span(
            f"agent.get_capabilities.{self.name}"
        ) as span:
            span.set_attribute("name", self.name)
            span.set_attribute("server_name", server_name)
            span.set_attribute("initialized", self.initialized)

            if not self.initialized:
                await self.initialize()

            executor = self.context.executor
            result: Dict[str, ServerCapabilities] = await executor.execute(
                self._agent_tasks.get_capabilities_task,
                GetCapabilitiesRequest(agent_name=self.name, server_name=server_name),
            )

            # If server_name is None, return all server capabilities
            if server_name is None:
                for server, capabilities in result.items():
                    for attr in ["logging", "prompts", "tools", "experimental"]:
                        value = getattr(capabilities, attr, None)
                        span.set_attribute(
                            f"{server}.capabilities.{attr}", value is not None
                        )
                return result
            # If server_name is provided, return the capabilities for that server
            elif server_name in result:
                capabilities = result[server_name]
                for attr in ["logging", "prompts", "tools", "experimental"]:
                    value = getattr(capabilities, attr, None)
                    span.set_attribute(
                        f"{server_name}.capabilities.{attr}", value is not None
                    )
                return capabilities
            else:
                raise ValueError(
                    f"Server '{server_name}' not found in agent '{self.name}'. "
                    f"Available servers: {list(result.keys())}"
                )

    async def list_tools(self, server_name: str | None = None) -> ListToolsResult:
        tracer = self.context.tracer or trace.get_tracer("mcp-agent")
        with tracer.start_as_current_span(f"agent.list_tools.{self.name}") as span:
            span.set_attribute("name", self.name)
            span.set_attribute("server_name", server_name)
            span.set_attribute("initialized", self.initialized)
            span.set_attribute(
                "human_input_callback", self.human_input_callback is not None
            )

            if not self.initialized:
                await self.initialize()

            if server_name:
                result = ListToolsResult(
                    tools=[
                        namespaced_tool.tool.model_copy(
                            update={"name": namespaced_tool.namespaced_tool_name}
                        )
                        for namespaced_tool in self._server_to_tool_map.get(
                            server_name, []
                        )
                    ]
                )
            else:
                result = ListToolsResult(
                    tools=[
                        namespaced_tool.tool.model_copy(
                            update={"name": namespaced_tool_name}
                        )
                        for namespaced_tool_name, namespaced_tool in self._namespaced_tool_map.items()
                    ]
                )

            # Add function tools
            for tool in self._function_tool_map.values():
                result.tools.append(
                    Tool(
                        name=tool.name,
                        description=tool.description,
                        inputSchema=tool.parameters,
                    )
                )

            # Add a human_input_callback as a tool
            if not self.human_input_callback:
                logger.debug("Human input callback not set")

                for tool in result.tools:
                    span.set_attribute(
                        f"tool.{tool.name}.description", tool.description
                    )
                    span.set_attribute(
                        f"tool.{tool.name}.inputSchema", json.dumps(tool.inputSchema)
                    )
                    if tool.annotations:
                        for attr in [
                            "title",
                            "readOnlyHint",
                            "destructiveHint",
                            "idempotentHint",
                            "openWorldHint",
                        ]:
                            value = getattr(tool.annotations, attr, None)
                            if value is not None:
                                span.set_attribute(
                                    f"tool.{tool.name}.annotations.{attr}", value
                                )

                return result

            # Add a human_input_callback as a tool
            human_input_tool: FastTool = FastTool.from_function(
                self.request_human_input
            )
            result.tools.append(
                Tool(
                    name=HUMAN_INPUT_TOOL_NAME,
                    description=human_input_tool.description,
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "request": HumanInputRequest.model_json_schema()
                        },
                        "required": ["request"],
                    },
                )
            )

            for tool in result.tools:
                span.set_attribute(f"tool.{tool.name}.description", tool.description)
                span.set_attribute(
                    f"tool.{tool.name}.inputSchema", json.dumps(tool.inputSchema)
                )
                if tool.annotations:
                    for attr in [
                        "title",
                        "readOnlyHint",
                        "destructiveHint",
                        "idempotentHint",
                        "openWorldHint",
                    ]:
                        value = getattr(tool.annotations, attr, None)
                        if value is not None:
                            span.set_attribute(
                                f"tool.{tool.name}.annotations.{attr}", value
                            )

            return result

    async def list_prompts(self, server_name: str | None = None) -> ListPromptsResult:
        if not self.initialized:
            await self.initialize()

        executor = self.context.executor
        result: ListPromptsResult = await executor.execute(
            self._agent_tasks.list_prompts_task,
            ListToolsRequest(agent_name=self.name, server_name=server_name),
        )

        return result

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> GetPromptResult:
        if not self.initialized:
            await self.initialize()

        executor = self.context.executor
        result: GetPromptResult = await executor.execute(
            self._agent_tasks.get_prompt_task,
            GetPromptRequest(agent_name=self.name, name=name, arguments=arguments),
        )

        return result

    async def request_human_input(
        self,
        request: HumanInputRequest,
    ) -> str:
        """
        Request input from a human user. Pauses the workflow until input is received.

        Args:
            request: The human input request

        Returns:
            The input provided by the human

        Raises:
            TimeoutError: If the timeout is exceeded
            ValueError: If human_input_callback is not set or doesn't have the right signature
        """
        if not self.human_input_callback:
            raise ValueError("Human input callback not set")

        # Generate a unique ID for this request to avoid signal collisions
        request_id = f"{HUMAN_INPUT_SIGNAL_NAME}_{self.name}_{uuid.uuid4()}"
        request.request_id = request_id

        logger.debug("Requesting human input:", data=request)

        async def call_callback_and_signal():
            try:
                user_input = await self.human_input_callback(request)
                logger.debug("Received human input:", data=user_input)
                await self.context.executor.signal(
                    signal_name=request_id, payload=user_input
                )
            except Exception as e:
                await self.context.executor.signal(
                    request_id, payload=f"Error getting human input: {str(e)}"
                )

        asyncio.create_task(call_callback_and_signal())

        logger.debug("Waiting for human input signal")

        # Wait for signal (workflow is paused here)
        result = await self.context.executor.wait_for_signal(
            signal_name=request_id,
            request_id=request_id,
            workflow_id=request.workflow_id,
            signal_description=request.description or request.prompt,
            timeout_seconds=request.timeout_seconds,
            signal_type=HumanInputResponse,  # TODO: saqadri - should this be HumanInputResponse?
        )

        logger.debug("Received human input signal", data=result)
        return result

    async def call_tool(
        self, name: str, arguments: dict | None = None, server_name: str | None = None
    ) -> CallToolResult:
        # Call the tool on the server
        if not self.initialized:
            await self.initialize()

        if name == HUMAN_INPUT_TOOL_NAME:
            # Call the human input tool
            return await self._call_human_input_tool(arguments)
        elif name in self._function_tool_map:
            # Call local function and return the result as a text response
            tool = self._function_tool_map[name]
            result = await tool.run(arguments)
            return CallToolResult(content=[TextContent(type="text", text=str(result))])
        else:
            executor = self.context.executor
            result: CallToolResult = await executor.execute(
                self._agent_tasks.call_tool_task,
                CallToolRequest(
                    agent_name=self.name,
                    name=name,
                    arguments=arguments,
                    server_name=server_name,
                ),
            )

            return result

    async def _call_human_input_tool(
        self, arguments: dict | None = None
    ) -> CallToolResult:
        # Handle human input request
        try:
            request = HumanInputRequest(**arguments["request"])
            result: HumanInputResponse = await self.request_human_input(request=request)
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text=f"Human response: {result.model_dump_json()}"
                    )
                ]
            )
        except TimeoutError as e:
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Error: Human input request timed out: {str(e)}",
                    )
                ],
            )
        except Exception as e:
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text", text=f"Error requesting human input: {str(e)}"
                    )
                ],
            )


class InitAggregatorRequest(BaseModel):
    """
    Request to load/initialize an agent's servers.
    """

    agent_name: str
    server_names: List[str]
    connection_persistence: bool = True
    force: bool = False


class InitAggregatorResponse(BaseModel):
    """
    Response for the load server request.
    """

    initialized: bool

    namespaced_tool_map: Dict[str, NamespacedTool] = Field(default_factory=dict)
    server_to_tool_map: Dict[str, List[NamespacedTool]] = Field(default_factory=dict)

    namespaced_prompt_map: Dict[str, NamespacedPrompt] = Field(default_factory=dict)
    server_to_prompt_map: Dict[str, List[NamespacedPrompt]] = Field(
        default_factory=dict
    )


class ListToolsRequest(BaseModel):
    """
    Request to list tools for an agent.
    """

    agent_name: str
    server_name: Optional[str] = None


class CallToolRequest(BaseModel):
    """
    Request to call a tool for an agent.
    """

    agent_name: str
    server_name: Optional[str] = None

    name: str
    arguments: Optional[dict[str, str]] = None


class ListPromptsRequest(BaseModel):
    """
    Request to list prompts for an agent.
    """

    agent_name: str
    server_name: Optional[str] = None


class GetPromptRequest(BaseModel):
    """
    Request to get a prompt from an agent.
    """

    agent_name: str
    server_name: Optional[str] = None

    name: str
    arguments: Optional[dict[str, str]] = None


class GetCapabilitiesRequest(BaseModel):
    """
    Request to get the capabilities of a specific server.
    """

    agent_name: str
    server_name: Optional[str] = None


class AgentTasks:
    """
    Agent tasks for executing agent-related activities.
    """

    # --- global-per-worker state -------------------------------------------------
    # Maps agent name to its corresponding MCPAggregator
    server_aggregators_for_agent: Dict[str, MCPAggregator] = {}
    server_aggregators_for_agent_lock: asyncio.Lock = asyncio.Lock()
    # Maps agent name to its reference count
    agent_refcounts: dict[str, int] = {}
    # ---------------------------------------------------------------------------

    def __init__(self, context: "Context"):
        self.context = context

    async def initialize_aggregator_task(
        self, request: InitAggregatorRequest
    ) -> InitAggregatorResponse:
        """
        Load/initialize an agent's servers.
        """
        agent_name = request.agent_name
        server_names = request.server_names
        connection_persistence = request.connection_persistence

        # Create or get the MCPAggregator for the agent
        async with self.server_aggregators_for_agent_lock:
            aggregator = self.server_aggregators_for_agent.get(request.agent_name)
            refcount = self.agent_refcounts.get(agent_name, 0)
            if not aggregator:
                aggregator = MCPAggregator(
                    server_names=server_names,
                    connection_persistence=connection_persistence,
                    context=self.context,
                    name=request.agent_name,
                )
                self.server_aggregators_for_agent[request.agent_name] = aggregator

            # Bump the reference counter
            self.agent_refcounts[agent_name] = refcount + 1

        # Initialize the servers
        aggregator = self.server_aggregators_for_agent[agent_name]
        await aggregator.initialize(force=request.force)

        return InitAggregatorResponse(
            initialized=aggregator.initialized,
            namespaced_tool_map=aggregator._namespaced_tool_map,
            server_to_tool_map=aggregator._server_to_tool_map,
            namespaced_prompt_map=aggregator._namespaced_prompt_map,
            server_to_prompt_map=aggregator._server_to_prompt_map,
        )

    async def shutdown_aggregator_task(self, agent_name: str) -> bool:
        """
        Shutdown the agent's servers.
        """

        async with self.server_aggregators_for_agent_lock:
            refcount = self.agent_refcounts.get(agent_name)
            if refcount is None:
                # Nothing to do – shutdown called more often than initialize
                return True

            if refcount > 1:
                # Still outstanding agent refs – just decrement and exit
                self.agent_refcounts[agent_name] = refcount - 1
                return True

            # refcount is 1 – this is the last shutdown
            server_aggregator = self.server_aggregators_for_agent.pop(agent_name, None)
            self.agent_refcounts.pop(agent_name, None)

        if server_aggregator:
            await server_aggregator.close()

        return True

    async def list_tools_task(self, request: ListToolsRequest) -> ListToolsResult:
        """
        List tools for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        # Get the MCPAggregator for the agent
        aggregator = self.server_aggregators_for_agent.get(agent_name)
        if not aggregator:
            raise ValueError(f"Server aggregrator for agent '{agent_name}' not found")

        return await aggregator.list_tools(server_name=server_name)

    async def call_tool_task(self, request: CallToolRequest) -> CallToolResult:
        """
        Call a tool for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        # Get the MCPAggregator for the agent
        aggregator = self.server_aggregators_for_agent.get(agent_name)
        if not aggregator:
            raise ValueError(f"Server aggregrator for agent '{agent_name}' not found")

        return await aggregator.call_tool(
            name=request.name, arguments=request.arguments, server_name=server_name
        )

    async def list_prompts_task(self, request: ListPromptsRequest) -> ListPromptsResult:
        """
        List tools for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        # Get the MCPAggregator for the agent
        aggregator = self.server_aggregators_for_agent.get(agent_name)
        if not aggregator:
            raise ValueError(f"Server aggregrator for agent '{agent_name}' not found")

        return await aggregator.list_prompts(server_name=server_name)

    async def get_prompt_task(self, request: GetPromptRequest) -> GetPromptResult:
        """
        Get a prompt for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        # Get the MCPAggregator for the agent
        aggregator = self.server_aggregators_for_agent.get(agent_name)
        if not aggregator:
            raise ValueError(f"Server aggregrator for agent '{agent_name}' not found")

        return await aggregator.get_prompt(
            name=request.name, arguments=request.arguments, server_name=server_name
        )

    async def get_capabilities_task(
        self, request: GetCapabilitiesRequest
    ) -> Dict[str, ServerCapabilities]:
        """
        Get the capabilities of a specific server.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        # Get the MCPAggregator for the agent
        aggregator = self.server_aggregators_for_agent.get(agent_name)
        if not aggregator:
            raise ValueError(f"Server aggregrator for agent '{agent_name}' not found")

        server_capabilities: Dict[str, ServerCapabilities] = {}

        if not server_name:
            # If no server name is provided, get capabilities for all servers
            server_names: List[str] = aggregator.server_names
            capabilities: List[ServerCapabilities] = await asyncio.gather(
                *[aggregator.get_capabilities(server_name=n) for n in server_names],
                return_exceptions=True,  # propagate exceptions – change if you want to swallow them
            )

            server_capabilities = dict(zip(server_names, capabilities))

        else:
            # If a server name is provided, get capabilities for that server
            server_capabilities[server_name] = await aggregator.get_capabilities(
                server_name=server_name
            )

        return server_capabilities
