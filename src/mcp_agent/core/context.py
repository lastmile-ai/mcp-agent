"""
A central context object to store global state that is shared across the application.
"""

import asyncio
import concurrent.futures
from typing import Any, Optional, TYPE_CHECKING
import uuid

from pydantic import BaseModel, ConfigDict

from mcp import ServerSession

from opentelemetry import trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from mcp_agent.config import get_settings
from mcp_agent.config import Settings
from mcp_agent.executor.executor import Executor
from mcp_agent.executor.decorator_registry import (
    DecoratorRegistry,
    register_asyncio_decorators,
    register_temporal_decorators,
)
from mcp_agent.executor.signal_registry import SignalRegistry
from mcp_agent.executor.task_registry import ActivityRegistry
from mcp_agent.executor.executor import AsyncioExecutor

from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.logging.transport import create_transport
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from mcp_agent.logging.logger import get_logger


if TYPE_CHECKING:
    from mcp_agent.human_input.types import HumanInputCallback
    from mcp_agent.executor.workflow_signal import SignalWaitCallback
    from mcp_agent.executor.workflow import WorkflowRegistry
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

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,  # Tell Pydantic to defer type evaluation
    )


async def configure_otel(config: "Settings"):
    """
    Configure OpenTelemetry based on the application config.
    """
    if not config.otel.enabled:
        return

    # Check if a provider is already set to avoid re-initialization
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        logger.info(
            f"Otel tracer provider already set: {trace.get_tracer_provider().__class__.__name__}"
        )
        return

    # Set up global textmap propagator first
    set_global_textmap(TraceContextTextMapPropagator())

    # pylint: disable=import-outside-toplevel (do not import if otel is not enabled)
    from importlib.metadata import version

    service_version = config.otel.service_version
    if not service_version:
        try:
            service_version = version("mcp-agent")
        # pylint: disable=broad-exception-caught
        except Exception:
            service_version = "unknown"

    service_name = config.otel.service_name
    service_instance_id = config.otel.service_instance_id or str(uuid.uuid4())[:6]

    # Create resource identifying this service
    resource = Resource.create(
        attributes={
            key: value
            for key, value in {
                "service.name": service_name,
                "service.instance.id": service_instance_id,
                "service.version": service_version,
            }.items()
            if value is not None
        }
    )

    # Create provider with resource
    tracer_provider = TracerProvider(resource=resource)

    # Add exporters based on config
    otlp_endpoint = config.otel.otlp_endpoint
    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        if config.otel.console_debug:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
    else:
        # Default to console exporter in development
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set as global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Set up autoinstrumentation
    # pylint: disable=import-outside-toplevel (do not import if otel is not enabled)
    from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor

    AnthropicInstrumentor().instrument()
    OpenAIInstrumentor().instrument()


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

    # Import here to avoid circular imports
    from mcp_agent.executor.workflow import WorkflowRegistry

    context.workflow_registry = WorkflowRegistry()

    # Configure logging and telemetry
    await configure_otel(config)
    await configure_logger(config, context.session_id)
    await configure_usage_telemetry(config)

    # Configure the executor
    context.executor = await configure_executor(config)

    context.session_id = str(context.executor.uuid())

    context.task_registry = task_registry or ActivityRegistry()

    context.signal_registry = signal_registry or SignalRegistry()

    if not decorator_registry:
        context.decorator_registry = DecoratorRegistry()
        register_asyncio_decorators(context.decorator_registry)
        register_temporal_decorators(context.decorator_registry)
    else:
        context.decorator_registry = decorator_registry

    # Store the tracer in context if needed
    context.tracer = trace.get_tracer(config.otel.service_name)

    if store_globally:
        global _global_context
        _global_context = context

    return context


async def cleanup_context():
    """
    Cleanup the global application context.
    """

    # Shutdown logging and telemetry
    await LoggingConfig.shutdown()


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
    return _global_context


def get_current_config():
    """
    Get the current application config.
    """
    return get_current_context().config or get_settings()
