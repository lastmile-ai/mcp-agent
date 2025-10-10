"""
A central context object to store global state that is shared across the application.
"""

import asyncio
import concurrent.futures
from typing import Any, List, Optional, TYPE_CHECKING, Literal
import warnings

from pydantic import ConfigDict

from mcp import ServerSession
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context as MCPContext

from opentelemetry import trace

from mcp_agent.config import get_settings
from mcp_agent.config import Settings
from mcp_agent.executor.executor import AsyncioExecutor, Executor
from mcp_agent.executor.decorator_registry import (
    DecoratorRegistry,
    register_asyncio_decorators,
    register_temporal_decorators,
)
from mcp_agent.executor.signal_registry import SignalRegistry
from mcp_agent.executor.task_registry import ActivityRegistry

from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.logging.transport import create_transport
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.tracing.tracer import TracingConfig
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from mcp_agent.logging.logger import get_logger
from mcp_agent.tracing.token_counter import TokenCounter


if TYPE_CHECKING:
    from mcp_agent.agents.agent_spec import AgentSpec
    from mcp_agent.app import MCPApp
    from mcp_agent.elicitation.types import ElicitationCallback
    from mcp_agent.executor.workflow_signal import SignalWaitCallback
    from mcp_agent.executor.workflow_registry import WorkflowRegistry
    from mcp_agent.human_input.types import HumanInputCallback
    from mcp_agent.logging.logger import Logger
else:
    # Runtime placeholders for the types
    AgentSpec = Any
    HumanInputCallback = Any
    ElicitationCallback = Any
    SignalWaitCallback = Any
    WorkflowRegistry = Any
    MCPApp = Any
    Logger = Any

logger = get_logger(__name__)


class Context(MCPContext):
    """
    Context that is passed around through the application.
    This is a global context that is shared across the application.
    """

    config: Optional[Settings] = None
    executor: Optional[Executor] = None
    human_input_handler: Optional[HumanInputCallback] = None
    elicitation_handler: Optional[ElicitationCallback] = None
    signal_notification: Optional[SignalWaitCallback] = None
    upstream_session: Optional[ServerSession] = None
    model_selector: Optional[ModelSelector] = None
    session_id: str | None = None
    app: Optional["MCPApp"] = None

    # Subagents
    loaded_subagents: List["AgentSpec"] = []

    # Registries
    server_registry: Optional[ServerRegistry] = None
    task_registry: Optional[ActivityRegistry] = None
    signal_registry: Optional[SignalRegistry] = None
    decorator_registry: Optional[DecoratorRegistry] = None
    workflow_registry: Optional["WorkflowRegistry"] = None

    tracer: Optional[trace.Tracer] = None
    # Use this flag to conditionally serialize expensive data for tracing
    tracing_enabled: bool = False
    # Store the TracingConfig instance for this context
    tracing_config: Optional[TracingConfig] = None

    # Token counting and cost tracking
    token_counter: Optional[TokenCounter] = None

    # Dynamic gateway configuration (per-run overrides via Temporal memo)
    gateway_url: str | None = None
    gateway_token: str | None = None

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,  # Tell Pydantic to defer type evaluation
    )

    @property
    def mcp(self) -> FastMCP | None:
        return self.app.mcp if self.app else None

    @property
    def fastmcp(self) -> FastMCP | None:  # type: ignore[override]
        """Return the FastMCP instance if available.

        Prefer the active request-bound FastMCP instance if present; otherwise
        fall back to the app's configured FastMCP server. Returns None if neither
        is available. This is more forgiving than the FastMCP Context default,
        which raises outside of a request.
        """
        try:
            # Prefer a request-bound fastmcp if set by FastMCP during a request
            if getattr(self, "_fastmcp", None) is not None:
                return getattr(self, "_fastmcp", None)
        except Exception:
            pass
        # Fall back to app-managed server instance (may be None in local scripts)
        return self.mcp

    @property
    def session(self) -> ServerSession | None:
        """Best-effort ServerSession for upstream communication.

        Priority:
        - If explicitly provided, use `upstream_session`.
        - If running within an active FastMCP request, use parent session.
        - If an app FastMCP exists, use its current request context if any.

        Returns None when no session can be resolved (e.g., local scripts).
        """
        # 1) Explicit upstream session set by app/workflow
        if getattr(self, "upstream_session", None) is not None:
            return self.upstream_session

        # 2) Try request-scoped session from FastMCP Context (may raise outside requests)
        try:
            return super().session  # type: ignore[misc]
        except Exception:
            pass

        # 3) Fall back to FastMCP server's current context if available
        try:
            mcp = self.mcp
            if mcp is not None:
                ctx = mcp.get_context()
                # FastMCP.get_context returns a Context that raises outside a request;
                # guard accordingly.
                try:
                    return getattr(ctx, "session", None)
                except Exception:
                    return None
        except Exception:
            pass

        # No session available in this runtime mode
        return None

    @property
    def logger(self) -> "Logger | None":
        return self.app.logger if self.app else None

    # ---- FastMCP Context method fallbacks (safe outside requests) ---------

    def bind_request(
        self, request_context: Any, fastmcp: FastMCP | None = None
    ) -> "Context":
        """Return a shallow-copied Context bound to a specific FastMCP request.

        - Shares app-wide state (config, registries, token counter, etc.) with the original Context
        - Attaches `_request_context` and `_fastmcp` so FastMCP Context APIs work during the request
        - Does not mutate the original Context (safe for concurrent requests)
        """
        # Shallow copy to preserve references to registries/loggers while keeping isolation
        bound: Context = self.model_copy(deep=False)
        try:
            setattr(bound, "_request_context", request_context)
        except Exception:
            pass
        try:
            if fastmcp is None:
                fastmcp = getattr(self, "_fastmcp", None) or self.mcp
            setattr(bound, "_fastmcp", fastmcp)
        except Exception:
            pass
        return bound

    @property
    def client_id(self) -> str | None:  # type: ignore[override]
        try:
            return super().client_id  # type: ignore[misc]
        except Exception:
            return None

    @property
    def request_id(self) -> str:  # type: ignore[override]
        try:
            return super().request_id  # type: ignore[misc]
        except Exception:
            # Provide a stable-ish fallback based on app session if available
            try:
                return str(self.session_id) if getattr(self, "session_id", None) else ""
            except Exception:
                return ""

    async def log(
        self,
        level: "Literal['debug', 'info', 'warning', 'error']",
        message: str,
        *,
        logger_name: str | None = None,
    ) -> None:  # type: ignore[override]
        """Send a log to the client if possible; otherwise, log locally.

        Matches FastMCP Context API but avoids raising when no request context
        is active by falling back to the app's logger.
        """
        # If we have a live FastMCP request context, delegate to parent
        try:
            # will raise if request_context is not available
            _ = self.request_context  # type: ignore[attr-defined]
            return await super().log(level, message, logger_name=logger_name)  # type: ignore[misc]
        except Exception:
            pass

        # Fall back to local logger if available
        try:
            _logger = self.logger
            if _logger is not None:
                if level == "debug":
                    _logger.debug(message)
                elif level == "warning":
                    _logger.warning(message)
                elif level == "error":
                    _logger.error(message)
                else:
                    _logger.info(message)
        except Exception:
            # Swallow errors in fallback logging to avoid masking tool behavior
            pass

    async def report_progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:  # type: ignore[override]
        """Report progress to the client if a request is active.

        Outside of a request (e.g., local scripts), this is a no-op to avoid
        runtime errors as no progressToken exists.
        """
        try:
            _ = self.request_context  # type: ignore[attr-defined]
            return await super().report_progress(progress, total, message)  # type: ignore[misc]
        except Exception:
            # No-op when no active request context
            return None

    async def read_resource(self, uri: Any) -> Any:  # type: ignore[override]
        """Read a resource via FastMCP if possible; otherwise raise clearly.

        This provides a friendlier error outside of a request and supports
        fallback to the app's FastMCP instance if available.
        """
        # Use the parent implementation if request-bound fastmcp is available
        try:
            if getattr(self, "_fastmcp", None) is not None:
                return await super().read_resource(uri)  # type: ignore[misc]
        except Exception:
            pass

        # Fall back to app-managed FastMCP if present
        try:
            mcp = self.mcp
            if mcp is not None:
                return await mcp.read_resource(uri)  # type: ignore[no-any-return]
        except Exception:
            pass

        raise ValueError(
            "read_resource is only available when an MCP server is active."
        )


async def configure_otel(
    config: "Settings", session_id: str | None = None
) -> Optional[TracingConfig]:
    """
    Configure OpenTelemetry based on the application config.

    Returns:
        TracingConfig instance if OTEL is enabled, None otherwise
    """
    if not config.otel.enabled:
        return None

    tracing_config = TracingConfig()
    await tracing_config.configure(settings=config.otel, session_id=session_id)
    return tracing_config


async def configure_logger(
    config: "Settings",
    session_id: str | None = None,
    token_counter: TokenCounter | None = None,
):
    """
    Configure logging and tracing based on the application config.
    """
    event_filter: EventFilter = EventFilter(min_level=config.logger.level)
    logger.info(f"Configuring logger with level: {config.logger.level}")
    transport = create_transport(
        settings=config.logger, event_filter=event_filter, session_id=session_id
    )
    await LoggingConfig.configure(
        event_filter=event_filter,
        transport=transport,
        batch_size=config.logger.batch_size,
        flush_interval=config.logger.flush_interval,
        progress_display=config.logger.progress_display,
        token_counter=token_counter,
    )


async def configure_usage_telemetry(_config: "Settings"):
    """
    Configure usage telemetry based on the application config.
    TODO: saqadri - implement usage tracking
    """
    pass


async def configure_executor(config: "Settings"):
    """
    Configure the executor based on the application config.
    """
    if config.execution_engine == "asyncio":
        return AsyncioExecutor()
    elif config.execution_engine == "temporal":
        # Configure Temporal executor
        from mcp_agent.executor.temporal import TemporalExecutor

        executor = TemporalExecutor(config=config.temporal)
        return executor
    else:
        # Default to asyncio executor
        executor = AsyncioExecutor()
        return executor


async def configure_workflow_registry(config: "Settings", executor: Executor):
    """
    Configure the workflow registry based on the application config.
    """
    if config.execution_engine == "temporal":
        from mcp_agent.executor.temporal.workflow_registry import (
            TemporalWorkflowRegistry,
        )

        return TemporalWorkflowRegistry(executor=executor)
    else:
        # Default to local workflow registry
        from mcp_agent.executor.workflow_registry import InMemoryWorkflowRegistry

        return InMemoryWorkflowRegistry()


async def initialize_context(
    config: Optional["Settings"] = None,
    task_registry: Optional[ActivityRegistry] = None,
    decorator_registry: Optional[DecoratorRegistry] = None,
    signal_registry: Optional[SignalRegistry] = None,
    store_globally: bool = False,
):
    """
    Initialize the global application context.
    """
    if config is None:
        config = get_settings()

    context = Context()
    context.config = config
    context.server_registry = ServerRegistry(config=config)

    # Configure the executor
    context.executor = await configure_executor(config)
    context.workflow_registry = await configure_workflow_registry(
        config, context.executor
    )

    context.session_id = str(context.executor.uuid())

    # Initialize token counter with engine hint for fast path checks
    context.token_counter = TokenCounter(execution_engine=config.execution_engine)

    # Configure logging and telemetry
    context.tracing_config = await configure_otel(config, context.session_id)
    await configure_logger(config, context.session_id, context.token_counter)
    await configure_usage_telemetry(config)

    context.task_registry = task_registry or ActivityRegistry()

    context.signal_registry = signal_registry or SignalRegistry()

    if not decorator_registry:
        context.decorator_registry = DecoratorRegistry()
        register_asyncio_decorators(context.decorator_registry)
        register_temporal_decorators(context.decorator_registry)
    else:
        context.decorator_registry = decorator_registry

    # Store the tracer in context if needed
    if config.otel.enabled:
        context.tracing_enabled = True

        if context.tracing_config is not None:
            # Use the app-specific tracer from the TracingConfig
            context.tracer = context.tracing_config.get_tracer(config.otel.service_name)
        else:
            # Use the global tracer if TracingConfig is not set
            context.tracer = trace.get_tracer(config.otel.service_name)

    if store_globally:
        global _global_context
        _global_context = context

    return context


async def cleanup_context(shutdown_logger: bool = False):
    """
    Cleanup the global application context.

    Args:
        shutdown_logger: If True, completely shutdown OTEL infrastructure.
                      If False, just cleanup app-specific resources.
    """
    if shutdown_logger:
        # Shutdown logging and telemetry completely
        await LoggingConfig.shutdown()
    else:
        # Just cleanup app-specific resources
        pass


_global_context: Context | None = None


def get_current_context() -> Context:
    """
    Synchronous initializer/getter for global application context.
    For async usage, use aget_current_context instead.
    """
    global _global_context
    if _global_context is None:
        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop in a separate thread
                def run_async():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(initialize_context())

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    _global_context = pool.submit(run_async).result()
            else:
                _global_context = loop.run_until_complete(initialize_context())
        except RuntimeError:
            _global_context = asyncio.run(initialize_context())

        # Advisory: using a global context can cause cross-thread coupling
        warnings.warn(
            "get_current_context() created a global Context. "
            "In multithreaded runs, instantiate an MCPApp per thread and use app.context instead.",
            stacklevel=2,
        )
    return _global_context


def get_current_config():
    """
    Get the current application config.
    """
    return get_current_context().config or get_settings()
