"""Metrics helpers built on top of OpenTelemetry."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExportResult,
    MetricExporter,
    PeriodicExportingMetricReader,
)

try:  # pragma: no cover - optional dependency in some environments
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # type: ignore
        OTLPMetricExporter,
    )
except Exception:  # pragma: no cover
    OTLPMetricExporter = None  # type: ignore


DEFAULT_SERVICE_NAME = "mcp-agent"
_provider_lock = threading.Lock()
_provider_initialised = False


@dataclass(slots=True)
class MetricsConfig:
    """Configuration values for metrics initialisation."""

    service_name: str = DEFAULT_SERVICE_NAME
    otlp_endpoint: str | None = None
    export_interval: float = 60.0

    @classmethod
    def from_env(cls) -> "MetricsConfig":
        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            export_interval=float(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "60")),
        )


def init_metrics(config: MetricsConfig | None = None) -> MeterProvider:
    """Initialise the global MeterProvider in an idempotent manner."""

    global _provider_initialised

    with _provider_lock:
        if _provider_initialised:
            provider = metrics.get_meter_provider()
            if not isinstance(provider, MeterProvider):  # pragma: no cover
                raise RuntimeError("Meter provider already set by another library")
            return provider

        cfg = config or MetricsConfig.from_env()

        if cfg.otlp_endpoint and OTLPMetricExporter is not None:
            exporter = OTLPMetricExporter(endpoint=cfg.otlp_endpoint, timeout=5.0)
        else:  # pragma: no cover - fallback for local development
            exporter = _NullMetricExporter()

        reader = PeriodicExportingMetricReader(
            exporter=exporter,
            export_interval_millis=int(cfg.export_interval * 1000),
        )

        provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(provider)
        _provider_initialised = True
        return provider


def get_meter(name: str = DEFAULT_SERVICE_NAME):
    if not _provider_initialised:
        init_metrics()
    return metrics.get_meter(name)


class _NullMetricExporter(MetricExporter):  # pragma: no cover - simple stub
    def export(self, metrics_data, timeout_millis: int | None = None, **_: object) -> MetricExportResult:
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: int | None = None, **_: object) -> None:
        return None

    def force_flush(self, timeout_millis: int | None = None, **_: object) -> bool:
        return True


_meter = get_meter("mcp-agent.observability")

run_duration_ms = _meter.create_histogram(
    "run_duration_ms",
    unit="ms",
    description="Total duration of a run including all stages.",
)

assemble_duration_ms = _meter.create_histogram(
    "assemble_duration_ms",
    unit="ms",
    description="Time spent assembling context for a run.",
)

llm_latency_ms = _meter.create_histogram(
    "llm_latency_ms",
    unit="ms",
    description="Latency of calls to the LLM gateway.",
)

tool_latency_ms = _meter.create_histogram(
    "tool_latency_ms",
    unit="ms",
    description="Latency of MCP tool invocations.",
)

test_duration_ms = _meter.create_histogram(
    "test_duration_ms",
    unit="ms",
    description="Duration of automated test executions triggered by the agent.",
)

runs_total = _meter.create_counter(
    "runs_total",
    unit="1",
    description="Total number of runs observed grouped by final state.",
)

llm_tokens_input_total = _meter.create_counter(
    "llm_tokens_input_total",
    unit="1",
    description="Count of input tokens sent to language models.",
)

llm_tokens_output_total = _meter.create_counter(
    "llm_tokens_output_total",
    unit="1",
    description="Count of output tokens produced by language models.",
)

tool_errors_total = _meter.create_counter(
    "tool_errors_total",
    unit="1",
    description="Count of tool invocation failures grouped by error code.",
)

budget_exceeded_total = _meter.create_counter(
    "budget_exceeded_total",
    unit="1",
    description="Number of runs that exceeded their configured budget.",
)

sse_events_sent_total = _meter.create_counter(
    "sse_events_sent_total",
    unit="1",
    description="Number of SSE events emitted by the run loop.",
)


def register_queue_depth_callback(observe: callable) -> None:
    """Register a callback that reports the queue depth gauge."""

    def _callback(options: CallbackOptions) -> Iterable[Observation]:  # pragma: no cover - runtime callback
        depth = observe()
        if depth is None:
            return []
        return [Observation(depth)]

    _meter.create_observable_gauge(
        "queue_depth",
        callbacks=[_callback],
        description="Depth of the agent work queue.",
    )


runs_in_progress = _meter.create_up_down_counter(
    "runs_in_progress",
    unit="1",
    description="Current number of runs executing.",
)


__all__ = [
    "MetricsConfig",
    "init_metrics",
    "get_meter",
    "run_duration_ms",
    "assemble_duration_ms",
    "llm_latency_ms",
    "tool_latency_ms",
    "test_duration_ms",
    "runs_total",
    "llm_tokens_input_total",
    "llm_tokens_output_total",
    "tool_errors_total",
    "budget_exceeded_total",
    "sse_events_sent_total",
    "runs_in_progress",
    "register_queue_depth_callback",
]

