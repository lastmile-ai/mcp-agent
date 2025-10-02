import asyncio
import json
import uuid
from typing import Callable, Dict, List, Optional, Set, TypeVar, TYPE_CHECKING, Any
from contextlib import asynccontextmanager

from opentelemetry import trace
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, PrivateAttr

from mcp.server.fastmcp.tools import Tool as FastTool
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    Tool,
    ListResourcesResult,
    ReadResourceResult,
    PromptMessage,
    EmbeddedResource,
)

from mcp_agent.core.context import Context
from mcp_agent.tracing.semconv import GEN_AI_AGENT_NAME, GEN_AI_TOOL_NAME
from mcp_agent.tracing.telemetry import (
    annotate_span_for_call_tool_result,
    get_tracer,
    record_attributes,
)
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.mcp.mcp_aggregator import (
    MCPAggregator,
    NamespacedPrompt,
    NamespacedTool,
    NamespacedResource,
)
from mcp_agent.human_input.types import (
    HumanInputRequest,
    HumanInputResponse,
    HUMAN_INPUT_SIGNAL_NAME,
)

from mcp_agent.logging.logger import get_logger

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

    instruction: Optional[str | Callable[[Dict], str]] = "You are a helpful agent."
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

    # Maps namespaced_resource_name -> namespaced resource info
    _namespaced_resource_map: Dict[str, NamespacedResource] = PrivateAttr(
        default_factory=dict
    )
    # Cache for resource objects, maps server_name -> list of resource objects
    _server_to_resource_map: Dict[str, List[NamespacedResource]] = PrivateAttr(
        default_factory=dict
    )

    _agent_tasks: "AgentTasks" = PrivateAttr(default=None)
    _init_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    # endregion

    def model_post_init(self, __context) -> None:
        # Map function names to tools
        self._function_tool_map = {
            (tool := FastTool.from_function(fn)).name: tool for fn in self.functions
        }

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
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.attach_llm"
        ) as span:
            if llm:
                self.llm = llm
                llm.agent = self
                if not llm.instruction:
                    llm.instruction = self.instruction
            elif llm_factory:
                self.llm = llm_factory(agent=self)
            else:
                raise ValueError("Either llm_factory or llm must be provided")

            span.set_attribute("llm.class", self.llm.__class__.__name__)

            for attr in ["name", "provider"]:
                value = getattr(self.llm, attr, None)
                if value is not None:
                    span.set_attribute(f"llm.{attr}", value)
            return self.llm

    async def get_token_node(self, return_all_matches: bool = False):
        """Return this Agent's token node(s) from the global counter."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return [] if return_all_matches else None
        counter = self.context.token_counter
        return (
            await counter.get_agent_node(self.name, return_all_matches=True)
            if return_all_matches
            else await counter.get_agent_node(self.name)
        )

    async def get_token_usage(self):
        """Return aggregated token usage for this Agent (including children)."""
        node = await self.get_token_node()
        return node.get_usage() if node else None

    async def get_token_cost(self) -> float:
        """Return total cost for this Agent (including children)."""
        node = await self.get_token_node()
        return node.get_cost() if node else 0.0

    async def watch_tokens(
        self,
        callback,
        *,
        threshold: int | None = None,
        throttle_ms: int | None = None,
        include_subtree: bool = True,
    ) -> str | None:
        """Watch this Agent's token usage. Returns a watch_id or None if not available."""
        if not self.context or not getattr(self.context, "token_counter", None):
            return None
        counter = self.context.token_counter
        # If there are multiple nodes with the same agent name, register a name/type-based watch
        nodes = await counter.get_agent_node(self.name, return_all_matches=True)
        if isinstance(nodes, list) and len(nodes) > 1:
            return await counter.watch(
                callback,
                node_name=self.name,
                node_type="agent",
                threshold=threshold,
                throttle_ms=throttle_ms,
                include_subtree=include_subtree,
            )
        # Otherwise fall back to watching a specific resolved node
        node = (
            nodes[0]
            if isinstance(nodes, list) and nodes
            else await self.get_token_node()
        )
        if not node:
            return None
        return await node.watch(
            callback,
            threshold=threshold,
            throttle_ms=throttle_ms,
            include_subtree=include_subtree,
        )

    async def format_token_tree(self) -> str:
        node = await self.get_token_node()
        if not node:
            return "(no token usage)"
        return node.format_tree()

    async def initialize(self, force: bool = False):
        """Initialize the agent."""

        if self.initialized and not force:
            return

        if self.context is None:
            # Fall back to global context if available
            from mcp_agent.core.context import get_current_context

            # Advisory: obtaining a global context can be unsafe in multithreaded runs
            # Prefer explicitly setting agent.context = app.context when running per-thread apps
            self.context = get_current_context()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.initialize"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("server_names", self.server_names)
            span.set_attribute("connection_persistence", self.connection_persistence)
            span.set_attribute("force", force)

            async with self._init_lock:
                span.add_event("initialize_start")
                logger.debug(f"Initializing agent {self.name}...")

                if self._agent_tasks is None:
                    self._agent_tasks = AgentTasks(self.context)

                if self.human_input_callback is None:
                    ctx_handler = getattr(self.context, "human_input_handler", None)
                    if ctx_handler is not None:
                        self.human_input_callback = ctx_handler

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

                self._namespaced_resource_map.clear()
                self._namespaced_resource_map.update(result.namespaced_resource_map)

                self._server_to_resource_map.clear()
                self._server_to_resource_map.update(result.server_to_resource_map)

                self.initialized = result.initialized
                span.add_event("initialize_complete")
                logger.debug(f"Agent {self.name} initialized.")

    async def shutdown(self):
        """
        Shutdown the agent and close all MCP server connections.
        NOTE: This method is called automatically when the agent is used as an async context manager.
        """
        logger.debug(f"Shutting down agent {self.name}...")

        if not self.initialized:
            logger.debug(f"Agent {self.name} is not initialized, skipping shutdown.")
            return

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.shutdown"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
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

    async def close(self):
        """
        Close the agent and release all resources.
        Synonymous with shutdown.
        """
        await self.shutdown()

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()

    async def get_capabilities(
        self, server_name: str | None = None
    ) -> ServerCapabilities | Dict[str, ServerCapabilities]:
        """
        Get the capabilities of a specific server.
        """
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.get_capabilities"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)

            executor = self.context.executor
            result: Dict[str, ServerCapabilities] = await executor.execute(
                self._agent_tasks.get_capabilities_task,
                GetCapabilitiesRequest(agent_name=self.name, server_name=server_name),
            )

            def _annotate_span_for_capabilities(
                server_name: str, capabilities: ServerCapabilities
            ):
                if not self.context.tracing_enabled:
                    return
                for attr in [
                    "experimental",
                    "logging",
                    "prompts",
                    "resources",
                    "tools",
                ]:
                    value = getattr(capabilities, attr, None)
                    span.set_attribute(
                        f"{server_name}.capabilities.{attr}", value is not None
                    )

            # If server_name is None, return all server capabilities
            if server_name is None:
                span.set_attribute("server_name", server_name)
                for server_name, capabilities in result.items():
                    _annotate_span_for_capabilities(server_name, capabilities)
                return result
            # If server_name is provided, return the capabilities for that server
            elif server_name in result:
                capabilities = result[server_name]
                _annotate_span_for_capabilities(server_name, capabilities)
                return capabilities
            else:
                raise ValueError(
                    f"Server '{server_name}' not found in agent '{self.name}'. "
                    f"Available servers: {list(result.keys())}"
                )

    async def get_server_session(self, server_name: str):
        """
        Get the session data of a specific server.
        """
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.get_server_session"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)

            executor = self.context.executor
            result: GetServerSessionResponse = await executor.execute(
                self._agent_tasks.get_server_session,
                GetServerSessionRequest(agent_name=self.name, server_name=server_name),
            )

            return result

    def _should_include_non_namespaced_tool(
        self, tool_name: str, tool_filter: Dict[str, Set[str]] | None
    ) -> tuple[bool, str | None]:
        """
        Determine if a non-namespaced tool (function tool or human input) should be included.

        Uses the special reserved key "non_namespaced_tools" to filter function tools and human input.

        Returns: (should_include, filter_reason)
        - filter_reason is None if tool should be included, otherwise explains why filtered
        """
        if tool_filter is None:
            return True, None

        # Priority 1: Check non_namespaced_tools key (explicitly for non-namespaced tools)
        if "non_namespaced_tools" in tool_filter:
            if tool_name in tool_filter["non_namespaced_tools"]:
                return True, None
            else:
                return False, f"{tool_name} not in tool_filter[non_namespaced_tools]"

        # Priority 2: Check wildcard filter
        elif "*" in tool_filter:
            if tool_name in tool_filter["*"]:
                return True, None
            else:
                return False, f"{tool_name} not in tool_filter[*]"

        # No non_namespaced_tools key and no wildcard - include by default (no filter for non-namespaced)
        return True, None

    async def list_tools(
        self,
        server_name: str | None = None,
        tool_filter: Dict[str, Set[str]] | None = None,
    ) -> ListToolsResult:
        """
        List available tools with optional filtering.

        Args:
            server_name: Optional specific server to list tools from
            tool_filter: Optional dict mapping server names to sets of allowed tool names.
                        Special reserved keys:
                        - "*": Wildcard filter for servers without explicit filters
                        - "non_namespaced_tools": Filter for non-namespaced tools (function tools, human input)
        """
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.list_tools"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)
            span.set_attribute(
                "human_input_callback", self.human_input_callback is not None
            )

            # Track filtered tools for debugging and telemetry
            filtered_out_tools = []  # List of (tool_name, reason) tuples

            if server_name:
                span.set_attribute("server_name", server_name)
                # Get tools for specific server
                server_tools = self._server_to_tool_map.get(server_name, [])

                # Check if we should apply filtering for this specific server
                if tool_filter is not None and server_name in tool_filter:
                    # Server is explicitly in filter dict - apply its filter rules
                    # If tool_filter[server_name] is empty set, no tools will pass
                    # If tool_filter[server_name] has tools, only those will pass
                    allowed_tools = tool_filter[server_name]
                    result_tools = []
                    for namespaced_tool in server_tools:
                        if namespaced_tool.tool.name in allowed_tools:
                            result_tools.append(
                                namespaced_tool.tool.model_copy(
                                    update={
                                        "name": namespaced_tool.namespaced_tool_name
                                    }
                                )
                            )
                        else:
                            filtered_out_tools.append(
                                (
                                    namespaced_tool.namespaced_tool_name,
                                    f"Not in tool_filter[{server_name}]",
                                )
                            )
                    result = ListToolsResult(tools=result_tools)
                else:
                    # Either no filter at all (tool_filter is None) or
                    # this server is not in the filter dict (no filtering for this server)
                    # Include all tools from this server
                    result = ListToolsResult(
                        tools=[
                            namespaced_tool.tool.model_copy(
                                update={"name": namespaced_tool.namespaced_tool_name}
                            )
                            for namespaced_tool in server_tools
                        ]
                    )
            else:
                # No specific server requested - get tools from all servers
                if tool_filter is not None:
                    # Filter is active - check each tool's server against filter rules
                    filtered_tools = []
                    for (
                        namespaced_tool_name,
                        namespaced_tool,
                    ) in self._namespaced_tool_map.items():
                        should_include = False

                        # Priority 1: Check if tool's server has explicit filter rules
                        if namespaced_tool.server_name in tool_filter:
                            # Server has explicit filter - tool must be in the allowed set
                            if (
                                namespaced_tool.tool.name
                                in tool_filter[namespaced_tool.server_name]
                            ):
                                should_include = True
                            else:
                                filtered_out_tools.append(
                                    (
                                        namespaced_tool_name,
                                        f"Not in tool_filter[{namespaced_tool.server_name}]",
                                    )
                                )
                        # Priority 2: If no server-specific filter, check wildcard
                        elif "*" in tool_filter:
                            # Wildcard filter applies to servers without explicit filters
                            if namespaced_tool.tool.name in tool_filter["*"]:
                                should_include = True
                            else:
                                filtered_out_tools.append(
                                    (namespaced_tool_name, "Not in tool_filter[*]")
                                )
                        else:
                            # No explicit filter for this server and no wildcard
                            # Default behavior: include the tool (no filtering)
                            should_include = True

                        if should_include:
                            filtered_tools.append(
                                namespaced_tool.tool.model_copy(
                                    update={"name": namespaced_tool_name}
                                )
                            )
                    result = ListToolsResult(tools=filtered_tools)
                else:
                    # No filter at all - include everything
                    result = ListToolsResult(
                        tools=[
                            namespaced_tool.tool.model_copy(
                                update={"name": namespaced_tool_name}
                            )
                            for namespaced_tool_name, namespaced_tool in self._namespaced_tool_map.items()
                        ]
                    )

            # Add function tools (non-namespaced) with filtering
            # These use the special "non_namespaced_tools" key in tool_filter
            for tool in self._function_tool_map.values():
                should_include, filter_reason = (
                    self._should_include_non_namespaced_tool(tool.name, tool_filter)
                )

                if should_include:
                    result.tools.append(
                        Tool(
                            name=tool.name,
                            description=tool.description,
                            inputSchema=tool.parameters,
                        )
                    )
                elif filter_reason:
                    filtered_out_tools.append((tool.name, filter_reason))

            def _annotate_span_for_tools_result(result: ListToolsResult):
                if not self.context.tracing_enabled:
                    return
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

            # Add human_input_callback tool (non-namespaced) with filtering
            # This uses the special "non_namespaced_tools" key in tool_filter
            if self.human_input_callback:
                should_include, filter_reason = (
                    self._should_include_non_namespaced_tool(
                        HUMAN_INPUT_TOOL_NAME, tool_filter
                    )
                )

                if should_include:
                    human_input_tool: FastTool = FastTool.from_function(
                        self.request_human_input
                    )
                    result.tools.append(
                        Tool(
                            name=HUMAN_INPUT_TOOL_NAME,
                            description=human_input_tool.description,
                            inputSchema=human_input_tool.parameters,
                        )
                    )
                elif filter_reason:
                    filtered_out_tools.append((HUMAN_INPUT_TOOL_NAME, filter_reason))
            else:
                logger.debug("Human input callback not set")

            # Log and track filtering metrics if filter was applied
            if tool_filter is not None:
                span.set_attribute("tool_filter_applied", True)
                span.set_attribute("tools_included_count", len(result.tools))
                span.set_attribute("tools_filtered_out_count", len(filtered_out_tools))

                # Add telemetry for filtered tools (limit to first 20 to avoid span bloat)
                if self.context.tracing_enabled:
                    for i, (tool_name, reason) in enumerate(filtered_out_tools[:20]):
                        span.set_attribute(f"filtered_tool.{i}.name", tool_name)
                        span.set_attribute(f"filtered_tool.{i}.reason", reason)
                    if len(filtered_out_tools) > 20:
                        span.set_attribute("filtered_tools_truncated", True)

                # Log filtered tools for debugging
                if filtered_out_tools:
                    logger.debug(
                        f"Tool filter applied: {len(filtered_out_tools)} tools filtered out, "
                        f"{len(result.tools)} tools remaining. "
                        f"Filtered tools: {[name for name, _ in filtered_out_tools[:10]]}"
                        + ("..." if len(filtered_out_tools) > 10 else "")
                    )
                    # Log detailed reasons at trace level (if trace logging is available)
                    if logger.isEnabledFor(10):  # TRACE level is usually 10
                        for tool_name, reason in filtered_out_tools:
                            logger.log(10, f"Filtered out '{tool_name}': {reason}")
                else:
                    logger.debug(
                        f"Tool filter applied: All {len(result.tools)} tools passed the filter"
                    )

            _annotate_span_for_tools_result(result)

            return result

    async def list_resources(
        self, server_name: str | None = None
    ) -> ListResourcesResult:
        """
        List resources available to the agent from MCP servers.
        """
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.list_resources"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)
            if server_name:
                span.set_attribute("server_name", server_name)

            executor = self.context.executor
            result: ListResourcesResult = await executor.execute(
                self._agent_tasks.list_resources_task,
                ListResourcesRequest(agent_name=self.name, server_name=server_name),
            )
            return result

    async def read_resource(self, uri: str, server_name: str | None = None):
        """
        Read a resource from an MCP server.
        """
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.read_resource"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)
            span.set_attribute("uri", uri)
            if server_name:
                span.set_attribute("server_name", server_name)

            executor = self.context.executor
            result: ReadResourceResult = await executor.execute(
                self._agent_tasks.read_resource_task,
                ReadResourceRequest(
                    agent_name=self.name, uri=uri, server_name=server_name
                ),
            )
            return result

    async def create_prompt(
        self,
        *,
        prompt_name: str | None = None,
        arguments: dict[str, str] | None = None,
        resource_uris: list[str | AnyUrl] | str | AnyUrl | None = None,
        server_names: list[str] | None = None,
    ) -> list[PromptMessage]:
        """
        Create prompt messages from a prompt name and/or resource URIs.

        Args:
            prompt_name: Name of the prompt to retrieve
            arguments: Arguments for the prompt (only used with prompt_name)
            resource_uris: URI(s) of the resource(s) to retrieve. Can be a single URI or list of URIs.
            server_names: List of server names to search across. If None, searches across all servers the agent have access to.

        Returns:
            List of PromptMessage objects. If both prompt_name and resource_uris are provided,
            the results are combined with prompt messages first, then resource messages.

        Raises:
            ValueError: If neither prompt_name nor resource_uris are provided
        """
        if prompt_name is None and resource_uris is None:
            raise ValueError(
                "Must specify at least one of prompt_name or resource_uris"
            )

        messages = []

        # Use provided server_names or default to all servers
        target_servers = server_names or self.server_names

        # Get prompt messages if prompt_name is provided
        if prompt_name is not None:
            # Try to find the prompt across the specified servers
            prompt_found = False
            for server in target_servers:
                try:
                    result = await self.get_prompt(
                        prompt_name, arguments, server_name=server
                    )
                    if not getattr(result, "isError", False):
                        messages.extend(result.messages)
                        prompt_found = True
                        break
                except Exception:
                    # Continue to next server if this one fails
                    continue

            if not prompt_found:
                raise ValueError(
                    f"Prompt '{prompt_name}' not found in any of the specified servers: {target_servers}"
                )

        # Get resource messages if resource_uris is provided
        if resource_uris is not None:
            # Normalize to list
            if isinstance(resource_uris, (str, AnyUrl)):
                uris_list = [resource_uris]
            else:
                uris_list = resource_uris

            # Process each URI - try to find it across the specified servers
            for uri in uris_list:
                resource_found = False
                for server in target_servers:
                    try:
                        resource_result = await self.read_resource(str(uri), server)
                        resource_messages = [
                            PromptMessage(
                                role="user",
                                content=EmbeddedResource(
                                    type="resource", resource=content
                                ),
                            )
                            for content in resource_result.contents
                        ]
                        messages.extend(resource_messages)
                        resource_found = True
                        break
                    except Exception:
                        # Continue to next server if this one fails
                        continue

                if not resource_found:
                    raise ValueError(
                        f"Resource '{uri}' not found in any of the specified servers: {target_servers}"
                    )

        return messages

    async def list_prompts(self, server_name: str | None = None) -> ListPromptsResult:
        # Check if the agent is initialized
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.list_prompts"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.name)
            span.set_attribute("initialized", self.initialized)

            if server_name:
                span.set_attribute("server_name", server_name)

            executor = self.context.executor
            result: ListPromptsResult = await executor.execute(
                self._agent_tasks.list_prompts_task,
                ListPromptsRequest(agent_name=self.name, server_name=server_name),
            )

            if self.context.tracing_enabled:
                span.set_attribute(
                    "prompts", [prompt.name for prompt in result.prompts]
                )

                for prompt in result.prompts:
                    span.set_attribute(
                        f"prompt.{prompt.name}.description", prompt.description
                    )
                    for arg in prompt.arguments:
                        for attr in [
                            "description",
                            "required",
                        ]:
                            value = getattr(arg, attr, None)
                            if value is not None:
                                span.set_attribute(
                                    f"prompt.{prompt.name}.arguments.{arg.name}.{attr}",
                                    value,
                                )

            return result

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
        server_name: str | None = None,
    ) -> GetPromptResult:
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.get_prompt"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute("name", name)
                span.set_attribute(GEN_AI_AGENT_NAME, self.name)
                span.set_attribute("initialized", self.initialized)
                record_attributes(span, arguments, "arguments")

            executor = self.context.executor
            result: GetPromptResult = await executor.execute(
                self._agent_tasks.get_prompt_task,
                GetPromptRequest(
                    agent_name=self.name,
                    server_name=server_name,
                    name=name,
                    arguments=arguments,
                ),
            )

            if getattr(result, "isError", False):
                # TODO: Should we remove isError to conform to spec and raise or return ErrorData code -32602
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.record_exception(
                    Exception(result.description or "Error getting prompt")
                )

            if self.context.tracing_enabled:
                if result.description:
                    span.set_attribute("prompt.description", result.description)

                for idx, message in enumerate(result.messages):
                    span.set_attribute(f"prompt.message.{idx}.role", message.role)
                    span.set_attribute(
                        f"prompt.message.{idx}.content.type", message.content.type
                    )
                    if message.content.type == "text":
                        span.set_attribute(
                            f"prompt.message.{idx}.content.text", message.content.text
                        )

            return result

    async def request_human_input(
        self,
        request: HumanInputRequest,
    ) -> HumanInputResponse:
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
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.request_human_input"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.name)
                span.set_attribute("initialized", self.initialized)
                span.set_attribute("request.prompt", request.prompt)

                for attr in [
                    "description",
                    "request_id",
                    "workflow_id",
                    "timeout_seconds",
                ]:
                    value = getattr(request, attr, None)
                    if value is not None:
                        span.set_attribute(f"request.{attr}", value)

                if request.metadata:
                    record_attributes(span, request.metadata, "request.metadata")

            if not self.human_input_callback:
                raise ValueError("Human input callback not set")

            # Generate a unique ID for this request to avoid signal collisions
            request_id = f"{HUMAN_INPUT_SIGNAL_NAME}_{self.name}_{uuid.uuid4()}"
            request.request_id = request_id
            span.set_attribute("request_id", request_id)

            logger.debug("Requesting human input:", data=request)

            async def call_callback_and_signal():
                try:
                    user_input = await self.human_input_callback(request)
                    logger.debug("Received human input:", data=user_input)
                    if self.context.tracing_enabled:
                        span.add_event(
                            "human_input_received",
                            {
                                request_id: user_input.request_id,
                                "response": user_input.response,
                                "metadata": json.dumps(user_input.metadata or {}),
                            },
                        )

                    await self.context.executor.signal(
                        signal_name=request_id,
                        payload=user_input,
                        workflow_id=request.workflow_id,
                        run_id=request.run_id,
                    )
                except Exception as e:
                    await self.context.executor.signal(
                        request_id,
                        payload=f"Error getting human input: {str(e)}",
                        workflow_id=request.workflow_id,
                        run_id=request.run_id,
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

            if self.context.tracing_enabled:
                span.add_event(
                    "human_input_signal_received",
                    {
                        "signal_name": request_id,
                        "request_id": request.request_id,
                        "workflow_id": request.workflow_id,
                        "signal_description": request.description or request.prompt,
                        "timeout_seconds": request.timeout_seconds,
                        "response": result.response,
                    },
                )

            logger.debug("Received human input signal", data=result)
            return result

    async def call_tool(
        self, name: str, arguments: dict | None = None, server_name: str | None = None
    ) -> CallToolResult:
        # Call the tool on the server
        if not self.initialized:
            await self.initialize()

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.call_tool"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.name)
                span.set_attribute(GEN_AI_TOOL_NAME, name)
                span.set_attribute("initialized", self.initialized)

                if server_name:
                    span.set_attribute("server_name", server_name)

                if arguments is not None:
                    record_attributes(span, arguments, "arguments")

            def _annotate_span_for_result(result: CallToolResult):
                if not self.context.tracing_enabled:
                    return
                annotate_span_for_call_tool_result(span, result)

            if name == HUMAN_INPUT_TOOL_NAME:
                # Call the human input tool
                result = await self._call_human_input_tool(arguments)
                _annotate_span_for_result(result)
                return result
            elif name in self._function_tool_map:
                # Call local function and return the result as a text response
                tool = self._function_tool_map[name]
                result = await tool.run(arguments)
                result = CallToolResult(
                    content=[TextContent(type="text", text=str(result))]
                )
                _annotate_span_for_result(result)
                return result
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
                _annotate_span_for_result(result)
                return result

    async def _call_human_input_tool(
        self, arguments: dict | None = None
    ) -> CallToolResult:
        # Handle human input request
        try:
            request = self.context.executor.create_human_input_request(
                arguments["request"]
            )
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

    namespaced_resource_map: Dict[str, NamespacedResource] = Field(default_factory=dict)
    server_to_resource_map: Dict[str, List[NamespacedResource]] = Field(
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
    arguments: Optional[dict[str, Any]] = None


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


class GetServerSessionRequest(BaseModel):
    """
    Request to get the session data of a specific server.
    """

    agent_name: str
    server_name: str


class ListResourcesRequest(BaseModel):
    """
    Request to list resources for an agent.
    """

    agent_name: str
    server_name: Optional[str] = None


class ReadResourceRequest(BaseModel):
    """
    Request to read a resource for an agent.
    """

    agent_name: str
    uri: str
    server_name: Optional[str] = None


class GetServerSessionResponse(BaseModel):
    """
    Response to the get server session request.
    """

    session_id: str | None = None
    session_data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class AgentTasks:
    """
    Agent tasks for executing agent-related activities.
    """

    def __init__(self, context: "Context"):
        self.context = context
        # --- instance-scoped state (thread-safe for Temporal worker event loop) ---
        # Using instance attributes avoids cross-thread event loop affinity issues with asyncio.Lock
        # when activities run concurrently in Temporal workers or multi-threaded environments.
        self.server_aggregators_for_agent: Dict[str, MCPAggregator] = {}
        self.server_aggregators_for_agent_lock: asyncio.Lock = asyncio.Lock()
        self.agent_refcounts: dict[str, int] = {}
        # Track in-flight tasks per agent to avoid shutting down while calls are running
        self.agent_task_counts: dict[str, int] = {}
        # Track agents awaiting shutdown once in-flight tasks complete
        self.agent_shutdown_pending: set[str] = set()
        # Remember init params to allow lazy re-initialization if aggregator missing
        self._agent_init_params: dict[str, tuple[List[str], bool]] = {}

    @asynccontextmanager
    async def _with_aggregator(self, agent_name: str):
        """
        Acquire an agent's aggregator for the duration of an operation, tracking in-flight usage
        and performing lazy reinitialization if necessary.
        """
        aggregator: MCPAggregator | None = None
        aggregator_to_close: MCPAggregator | None = None

        # Acquire lock to read/create and increment in-flight count atomically
        async with self.server_aggregators_for_agent_lock:
            aggregator = self.server_aggregators_for_agent.get(agent_name)

            # If aggregator missing, try lazy re-init from stored params
            if aggregator is None:
                params = self._agent_init_params.get(agent_name)
                if params is not None:
                    server_names, connection_persistence = params
                    logger.debug(
                        f"Reinitializing aggregator for agent '{agent_name}'",
                        data={
                            "server_names": server_names,
                            "connection_persistence": connection_persistence,
                        },
                    )
                    aggregator = MCPAggregator(
                        server_names=server_names,
                        connection_persistence=connection_persistence,
                        context=self.context,
                        name=agent_name,
                    )
                    self.server_aggregators_for_agent[agent_name] = aggregator
                else:
                    # No way to reconstruct aggregator, fail clearly
                    raise ValueError(
                        f"Server aggregator for agent '{agent_name}' not found"
                    )

            # Increment in-flight usage
            self.agent_task_counts[agent_name] = (
                self.agent_task_counts.get(agent_name, 0) + 1
            )
            logger.debug(
                f"Agent '{agent_name}' in-flight +1",
                data={"inflight": self.agent_task_counts[agent_name]},
            )

        try:
            if not aggregator.initialized:
                await aggregator.initialize()
            yield aggregator
        finally:
            # Decrement and check for pending shutdown
            async with self.server_aggregators_for_agent_lock:
                remaining = self.agent_task_counts.get(agent_name, 0) - 1
                if remaining > 0:
                    self.agent_task_counts[agent_name] = remaining
                else:
                    self.agent_task_counts.pop(agent_name, None)
                    if agent_name in self.agent_shutdown_pending:
                        aggregator_to_close = self.server_aggregators_for_agent.pop(
                            agent_name, None
                        )
                        self.agent_shutdown_pending.discard(agent_name)
                logger.debug(
                    f"Agent '{agent_name}' in-flight -1",
                    data={
                        "remaining": self.agent_task_counts.get(agent_name, 0),
                        "pending_shutdown": agent_name in self.agent_shutdown_pending,
                        "will_close": aggregator_to_close is not None,
                    },
                )

            if aggregator_to_close is not None:
                try:
                    await aggregator_to_close.close()
                except Exception:
                    pass

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
            # Record init params for potential lazy re-initialization
            self._agent_init_params[agent_name] = (
                list(server_names) if isinstance(server_names, list) else [],
                bool(connection_persistence),
            )
            logger.debug(
                f"Initialized aggregator for agent '{agent_name}'",
                data={
                    "refcount": self.agent_refcounts[agent_name],
                    "server_names": server_names,
                    "connection_persistence": connection_persistence,
                },
            )

        # Initialize the servers
        aggregator = self.server_aggregators_for_agent[agent_name]
        await aggregator.initialize(force=request.force)

        return InitAggregatorResponse(
            initialized=aggregator.initialized,
            namespaced_tool_map=aggregator._namespaced_tool_map,
            server_to_tool_map=aggregator._server_to_tool_map,
            namespaced_prompt_map=aggregator._namespaced_prompt_map,
            server_to_prompt_map=aggregator._server_to_prompt_map,
            namespaced_resource_map=aggregator._namespaced_resource_map,
            server_to_resource_map=aggregator._server_to_resource_map,
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
                logger.debug(
                    f"Shutdown aggregator for agent '{agent_name}' deferred (refcount)",
                    data={"new_refcount": self.agent_refcounts[agent_name]},
                )
                return True

            # refcount is 1 – this is the last shutdown
            inflight = self.agent_task_counts.get(agent_name, 0)
            if inflight > 0:
                # Defer shutdown until in-flight tasks complete
                self.agent_refcounts.pop(agent_name, None)
                self.agent_shutdown_pending.add(agent_name)
                logger.debug(
                    f"Shutdown aggregator for agent '{agent_name}' deferred (in-flight)",
                    data={"inflight": inflight},
                )
                return True

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

        async with self._with_aggregator(agent_name) as aggregator:
            return await aggregator.list_tools(server_name=server_name)

    async def call_tool_task(self, request: CallToolRequest) -> CallToolResult:
        """
        Call a tool for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
            return await aggregator.call_tool(
                name=request.name, arguments=request.arguments, server_name=server_name
            )

    async def list_prompts_task(self, request: ListPromptsRequest) -> ListPromptsResult:
        """
        List tools for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
            return await aggregator.list_prompts(server_name=server_name)

    async def get_prompt_task(self, request: GetPromptRequest) -> GetPromptResult:
        """
        Get a prompt for an agent.
        """

        agent_name = request.agent_name
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
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

        async with self._with_aggregator(agent_name) as aggregator:
            server_capabilities: Dict[str, ServerCapabilities] = {}

            if not server_name:
                # If no server name is provided, get capabilities for all servers
                server_names: List[str] = aggregator.server_names
                capabilities: List[ServerCapabilities] = await asyncio.gather(
                    *[aggregator.get_capabilities(server_name=n) for n in server_names],
                    return_exceptions=True,
                )
                server_capabilities = dict(zip(server_names, capabilities))
            else:
                # If a server name is provided, get capabilities for that server
                server_capabilities[server_name] = await aggregator.get_capabilities(
                    server_name=server_name
                )

            return server_capabilities

    async def get_server_session(
        self, request: GetServerSessionRequest
    ) -> GetServerSessionResponse:
        """
        Get the session for a specific server.
        """
        agent_name = request.agent_name
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
            server_session: MCPAgentClientSession | None = await aggregator.get_server(
                server_name=server_name
            )
            if server_session is None:
                return GetServerSessionResponse(
                    error=f"Session unavailable for '{server_name}'"
                )
            get_id = getattr(server_session, "get_session_id", None)
            session_id = get_id() if callable(get_id) else None

            return GetServerSessionResponse(
                session_id=session_id,
            )

    async def list_resources_task(self, request: ListResourcesRequest):
        """
        List resources for an agent.
        """
        agent_name = request.agent_name
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
            return await aggregator.list_resources(server_name=server_name)

    async def read_resource_task(self, request: ReadResourceRequest):
        """
        Read a resource for an agent.
        """
        agent_name = request.agent_name
        uri = request.uri
        server_name = request.server_name

        async with self._with_aggregator(agent_name) as aggregator:
            return await aggregator.read_resource(uri=uri, server_name=server_name)
