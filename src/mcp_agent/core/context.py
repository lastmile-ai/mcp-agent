"""
A central context object to store global state that is shared across the application.
"""

import asyncio
import concurrent.futures
from typing import Any, List, Optional, TYPE_CHECKING
import warnings

from pydantic import BaseModel, ConfigDict

from mcp import ServerSession
from mcp.server.fastmcp import FastMCP

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
    from mcp_agent.human_input.types import HumanInputCallback
    from mcp_agent.elicitation.types import ElicitationCallback
    from mcp_agent.executor.workflow_signal import SignalWaitCallback
    from mcp_agent.executor.workflow_registry import WorkflowRegistry
    from mcp_agent.app import MCPApp
else:
    # Runtime placeholders for the types
    AgentSpec = Any
    HumanInputCallback = Any
    ElicitationCallback = Any
    SignalWaitCallback = Any
    WorkflowRegistry = Any
    MCPApp = Any

logger = get_logger(__name__)


class Context(BaseModel):
    """
    Context that is passed around through the application.
    This is a global context that is shared across the application.
    """

    config: Optional[Settings] = None
    executor: Optional[Executor] = None
    human_input_handler: Optional[HumanInputCallback] = None
    elicitation_handler: Optional[ElicitationCallback] = None
    signal_notification: Optional[SignalWaitCallback] = None
    upstream_session: Optional[ServerSession] = None  # TODO: saqadri - figure this out
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
