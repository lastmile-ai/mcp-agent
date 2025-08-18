import uuid

from opentelemetry import trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from mcp_agent.config import OpenTelemetrySettings
from mcp_agent.logging.logger import get_logger
from mcp_agent.tracing.file_span_exporter import FileSpanExporter

logger = get_logger(__name__)


class TracingConfig:
    """Configuration for the tracing system."""

    _global_provider_set = False  # Track if global provider has been set
    _instrumentation_initialized = (
        False  # Class variable to track global instrumentation
    )

    def __init__(self):
        self._tracer_provider = None

    async def configure(
        self,
        settings: OpenTelemetrySettings,
        session_id: str | None = None,
        force: bool = False,
    ):
        """
        Configure the tracing system.

        Args:
            settings: OpenTelemetry settings
            session_id: Optional session ID for exported traces
            force: Force reconfiguration even if already initialized
        """
        if not settings.enabled:
            logger.info("OpenTelemetry is disabled. Skipping configuration.")
            return

        # Check if we should skip configuration
        if self._tracer_provider and not force:
            logger.info(
                "Tracer provider already configured for this instance, skipping reconfiguration"
            )
            return

        # If force and we have an existing provider, shutdown
        if force and self._tracer_provider:
            logger.info("Force reconfiguring tracer provider")
            if hasattr(self._tracer_provider, "shutdown"):
                self._tracer_provider.shutdown()
            self._tracer_provider = None

        # Set up global textmap propagator first
        set_global_textmap(TraceContextTextMapPropagator())

        # pylint: disable=import-outside-toplevel (do not import if otel is not enabled)
        from importlib.metadata import version

        service_version = settings.service_version
        if not service_version:
            try:
                service_version = version("mcp-agent")
            # pylint: disable=broad-exception-caught
            except Exception:
                service_version = "unknown"

        session_id = session_id or str(uuid.uuid4())

        service_name = settings.service_name
        service_instance_id = settings.service_instance_id or session_id

        # Create resource identifying this service
        resource = Resource.create(
            attributes={
                key: value
                for key, value in {
                    "service.name": service_name,
                    "service.instance.id": service_instance_id,
                    "service.version": service_version,
                    "session.id": session_id,
                }.items()
                if value is not None
            }
        )

        # Create provider with resource
        tracer_provider = TracerProvider(resource=resource)

        for exporter in settings.exporters:
            if exporter == "console":
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(
                        ConsoleSpanExporter(service_name=settings.service_name)
                    )
                )
            elif exporter == "otlp":
                if settings.otlp_settings:
                    tracer_provider.add_span_processor(
                        BatchSpanProcessor(
                            OTLPSpanExporter(
                                endpoint=settings.otlp_settings.endpoint,
                                headers=settings.otlp_settings.headers,
                            )
                        )
                    )
                else:
                    logger.error(
                        "OTLP exporter is enabled but no OTLP settings endpoint is provided."
                    )
            elif exporter == "file":
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(
                        FileSpanExporter(
                            service_name=settings.service_name,
                            session_id=session_id,
                            path_settings=settings.path_settings,
                            custom_path=settings.path,
                        )
                    )
                )
                continue
            else:
                logger.error(
                    f"Unknown exporter '{exporter}' specified. Supported exporters: console, otlp, file."
                )

        # Store the tracer provider instance
        self._tracer_provider = tracer_provider

        # Only set the global provider once
        if not TracingConfig._global_provider_set and isinstance(
            trace.get_tracer_provider(), trace.ProxyTracerProvider
        ):
            trace.set_tracer_provider(tracer_provider)
            TracingConfig._global_provider_set = True
            logger.info(f"Set global tracer provider for service: {service_name}")
        else:
            logger.info(
                f"Global tracer provider already set, created local provider for service: {service_name}"
            )

        # Set up autoinstrumentation only once globally
        if not TracingConfig._instrumentation_initialized:
            # pylint: disable=import-outside-toplevel (do not import if otel is not enabled)
            try:
                from opentelemetry.instrumentation.anthropic import (
                    AnthropicInstrumentor,
                )

                if not AnthropicInstrumentor().is_instrumented_by_opentelemetry:
                    AnthropicInstrumentor().instrument()
            except ModuleNotFoundError:
                logger.error(
                    "Anthropic OTEL instrumentation not available. Please install opentelemetry-instrumentation-anthropic."
                )
            try:
                from opentelemetry.instrumentation.openai import OpenAIInstrumentor

                if not OpenAIInstrumentor().is_instrumented_by_opentelemetry:
                    OpenAIInstrumentor().instrument()
            except ModuleNotFoundError:
                logger.error(
                    "OpenAI OTEL instrumentation not available. Please install opentelemetry-instrumentation-anthropic."
                )

            TracingConfig._instrumentation_initialized = True

    def get_tracer(self, name: str):
        """Get a tracer from this configuration's provider."""
        if self._tracer_provider:
            return self._tracer_provider.get_tracer(name)
        return trace.get_tracer(name)

    async def flush(self, timeout_ms: int = 5000) -> bool:
        """
        Force flush all pending spans to ensure they are exported.

        Args:
            timeout_ms: Maximum time to wait for flush in milliseconds

        Returns:
            True if flush succeeded, False otherwise
        """
        if not self._tracer_provider:
            return True

        if hasattr(self._tracer_provider, "force_flush"):
            try:
                # force_flush returns True if all spans were successfully flushed
                success = self._tracer_provider.force_flush(timeout_millis=timeout_ms)
                if not success:
                    logger.warning(
                        f"Failed to flush all traces within {timeout_ms}ms timeout"
                    )
                return success
            except Exception as e:
                logger.error(f"Error flushing traces: {e}")
                return False

        return True

    def shutdown(self):
        """
        Shutdown the tracer provider and all its processors.
        This stops all background threads and ensures clean shutdown.
        """
        if not self._tracer_provider:
            return

        if hasattr(self._tracer_provider, "shutdown"):
            try:
                logger.debug("Shutting down tracer provider")
                self._tracer_provider.shutdown()
                self._tracer_provider = None
            except Exception as e:
                logger.error(f"Error shutting down tracer provider: {e}")
