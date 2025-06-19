"""
A central context object to store global state that is shared across the application.
"""

import asyncio
import concurrent.futures
import threading
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from mcp import ServerSession

from opentelemetry import trace

from mcp_agent.config import get_settings
from mcp_agent.config import Settings
from mcp_agent.executor.executor import AsyncioExecutor, Executor
from mcp_agent.executor.decorator_registry import (
    DecoratorRegistry,
    get_global_decorator_registry,
    register_asyncio_decorators,
    register_temporal_decorators,
)
from mcp_agent.executor.signal_registry import (
    SignalRegistry,
    get_global_signal_registry,
)
from mcp_agent.executor.task_registry import (
    ActivityRegistry,
    get_global_activity_registry,
)

from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.logging.transport import create_transport
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.tracing.tracer import TracingConfig
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from mcp_agent.logging.logger import get_logger


if TYPE_CHECKING:
    from mcp_agent.human_input.types import HumanInputCallback
    from mcp_agent.executor.workflow_signal import SignalWaitCallback
    from mcp_agent.executor.workflow_registry import WorkflowRegistry
    from mcp_agent.app import MCPApp
else:
    # Runtime placeholders for the types
    HumanInputCallback = Any
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
    signal_notification: Optional[SignalWaitCallback] = None
    upstream_session: Optional[ServerSession] = None  # TODO: saqadri - figure this out
    model_selector: Optional[ModelSelector] = None
    session_id: str | None = None
    app: Optional["MCPApp"] = None

    # Registries
    server_registry: Optional[ServerRegistry] = None
    task_registry: Optional[ActivityRegistry] = None
    signal_registry: Optional[SignalRegistry] = None
    decorator_registry: Optional[DecoratorRegistry] = None
    workflow_registry: Optional["WorkflowRegistry"] = None

    tracer: Optional[trace.Tracer] = None
    # Use this flag to conditionally serialize expensive data for tracing
    tracing_enabled: bool = False

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,  # Tell Pydantic to defer type evaluation
    )


async def configure_otel(config: "Settings", session_id: str | None = None):
    """
    Configure OpenTelemetry based on the application config.
    """
    if not config.otel.enabled:
        return

    await TracingConfig.configure(settings=config.otel, session_id=session_id)


async def configure_logger(config: "Settings", session_id: str | None = None):
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

    # Configure logging and telemetry
    await configure_otel(config, context.session_id)
    await configure_logger(config, context.session_id)
    await configure_usage_telemetry(config)

    context.task_registry = task_registry or get_global_activity_registry()

    context.signal_registry = signal_registry or get_global_signal_registry()

    if not decorator_registry:
        context.decorator_registry = get_global_decorator_registry()
        register_asyncio_decorators(context.decorator_registry)
        register_temporal_decorators(context.decorator_registry)
    else:
        context.decorator_registry = decorator_registry

    # Store the tracer in context if needed
    if config.otel.enabled:
        context.tracing_enabled = True
        context.tracer = trace.get_tracer(config.otel.service_name)

    if store_globally:
        global _thread_local
        _thread_local.context = context

    return context


async def cleanup_context():
    """
    Cleanup the thread-local application context.
    """
    # Clean up thread-local context and its resources
    if hasattr(_thread_local, "context") and _thread_local.context is not None:
        context = _thread_local.context

        # Clean up server connections first (before event loop closure)
        if context.server_registry and hasattr(
            context.server_registry, "connection_manager"
        ):
            try:
                logger.debug("Cleaning up server registry connection manager...")
                connection_manager = context.server_registry.connection_manager

                try:
                    await connection_manager.disconnect_all()
                except Exception as e:
                    logger.warning(
                        f"Timeout during disconnect_all(), forcing shutdown. Error: {e}"
                    )

                # Give a brief moment for subprocess transports to clean up
                await asyncio.sleep(0.1)

                # Mark the connection manager as inactive to avoid cross-context cleanup
                if (
                    hasattr(connection_manager, "_tg_active")
                    and connection_manager._tg_active
                ):
                    try:
                        connection_manager._tg_active = False
                        connection_manager._tg = None
                        logger.debug(
                            "Context cleanup: Connection manager marked as inactive"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Error during connection manager state cleanup: {e}"
                        )

            except Exception as e:
                logger.warning(f"Error during server connection cleanup: {e}")

        # Clear the context reference
        _thread_local.context = None

    # Shutdown logging and telemetry
    await LoggingConfig.shutdown()


# Thread-local storage for context instances
_thread_local = threading.local()


def get_current_context() -> Context:
    """
    Thread-local getter for application context.
    Each thread gets its own context instance.
    """
    global _thread_local
    if not getattr(_thread_local, "context", None):
        try:
            loop = asyncio.get_running_loop()

            def run_async():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(initialize_context())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as pool:
                _thread_local.context = pool.submit(run_async).result()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _thread_local.context = loop.run_until_complete(initialize_context())
    return _thread_local.context


def reset_thread_context():
    """
    Reset the thread-local context for the current thread.
    Useful for ensuring clean state in multithreaded environments.
    """
    if hasattr(_thread_local, "context"):
        _thread_local.context = None


def get_current_config():
    """
    Get the current application config.
    """
    return get_current_context().config or get_settings()
