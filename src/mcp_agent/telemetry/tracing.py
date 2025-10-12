"""OpenTelemetry tracing helpers for the MCP agent.

This module centralises configuration of the OpenTelemetry tracer provider
and exposes a couple of convenience utilities that make it easy for the rest
of the code base to participate in tracing without having to understand the
details of the SDK configuration.  The helpers intentionally avoid
initialising global state at import time so that unit tests can exercise the
logic without having to manipulate module level globals.

The implementation keeps the following goals in mind:

* Honour ``OTEL_EXPORTER_OTLP_ENDPOINT`` when present.  If the environment
  variable is unset we still configure a tracer provider so that spans created
  during tests can be inspected, but we avoid crashing because of missing
  exporters.
* Use a parent based sampler with a configurable ratio.  The ratio is sourced
  from ``OBS_SAMPLER_RATIO`` when available and defaults to ``0.1`` in order to
  keep the sampling behaviour predictable across different deployments.
* Provide helpers for creating spans associated with a particular run.  The
  helpers hide the boilerplate for tagging spans with ``run_id``/``trace_id``
  and for generating a trace identifier when the caller does not already have
  one.

The functions are intentionally small so that they can be composed in higher
level orchestration modules without introducing tight coupling.  This allows
tests to swap in in-memory exporters while still exercising the sampling logic
and attribute propagation.
"""

from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Optional

from opentelemetry import trace
from opentelemetry.trace import Link, Span, Status, StatusCode
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

try:  # pragma: no cover - optional dependency in some environments
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
except Exception:  # pragma: no cover - fallback when OTLP extras not installed
    OTLPSpanExporter = None  # type: ignore


DEFAULT_SERVICE_NAME = "mcp-agent"
_provider_lock = threading.Lock()
_provider_initialised = False


def _env_sampler_ratio(default: float = 0.1) -> float:
    """Read ``OBS_SAMPLER_RATIO`` from the environment."""

    raw = os.getenv("OBS_SAMPLER_RATIO")
    if raw is None:
        return default
    try:
        ratio = float(raw)
    except ValueError:
        return default
    if ratio < 0:
        return 0.0
    if ratio > 1:
        return 1.0
    return ratio


@dataclass(slots=True)
class TracingConfig:
    """Configuration options for :func:`init_tracing`."""

    service_name: str = DEFAULT_SERVICE_NAME
    otlp_endpoint: str | None = None
    sampler_ratio: float | None = None
    resource_attributes: Dict[str, Any] | None = None

    @classmethod
    def from_env(cls) -> "TracingConfig":
        """Build a configuration object from environment variables."""

        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            sampler_ratio=_env_sampler_ratio(),
        )


def init_tracing(config: TracingConfig | None = None) -> TracerProvider:
    """Initialise and register the global tracer provider.

    The initialisation is idempotent – the first invocation wins and subsequent
    calls simply return the already configured provider.  This mirrors the
    expectations of the OpenTelemetry SDK and keeps unit tests predictable.
    """

    global _provider_initialised

    with _provider_lock:
        if _provider_initialised:
            provider = trace.get_tracer_provider()
            if not isinstance(provider, TracerProvider):  # pragma: no cover
                raise RuntimeError("Tracer provider already set by another library")
            return provider

        cfg = config or TracingConfig.from_env()

        sampler_ratio = cfg.sampler_ratio if cfg.sampler_ratio is not None else _env_sampler_ratio()
        sampler = ParentBased(TraceIdRatioBased(sampler_ratio))

        resource = Resource.create({"service.name": cfg.service_name, **(cfg.resource_attributes or {})})
        provider = TracerProvider(resource=resource, sampler=sampler)

        if cfg.otlp_endpoint and OTLPSpanExporter is not None:
            exporter = OTLPSpanExporter(endpoint=cfg.otlp_endpoint, timeout=5.0)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        else:  # Provide a console exporter for local development / tests
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _provider_initialised = True
        return provider


def get_tracer(name: str = DEFAULT_SERVICE_NAME):
    """Return a tracer using the configured provider."""

    if not _provider_initialised:
        init_tracing()
    return trace.get_tracer(name)


def ensure_trace_id(trace_id: str | None = None) -> str:
    """Return a canonical 32 character hexadecimal trace identifier."""

    if trace_id:
        return trace_id.lower()
    return uuid.uuid4().hex


def _span_attributes(run_id: str, trace_id: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {"run.id": run_id, "trace.id": trace_id}
    if extra:
        attrs.update(extra)
    return attrs


@contextmanager
def run_stage_span(
    stage: str,
    *,
    run_id: str,
    trace_id: str,
    attributes: Optional[Dict[str, Any]] = None,
    links: Optional[Iterable[Link]] = None,
) -> Iterator[Span]:
    """Context manager that starts a span for a run stage."""

    tracer = get_tracer()
    span_name = f"run.{stage}"
    with tracer.start_as_current_span(
        span_name,
        attributes=_span_attributes(run_id, trace_id, attributes),
        links=list(links or ()),
    ) as span:
        yield span


def annotate_error(span: Span, *, outcome: str | None = None, error_code: str | None = None) -> None:
    """Add error metadata to a span.

    This helper keeps the logic in one place so that callers do not have to
    remember the exact attribute keys to use.
    """

    span.set_status(Status(StatusCode.ERROR))
    if outcome:
        span.set_attribute("run.outcome", outcome)
    if error_code:
        span.set_attribute("run.error_code", error_code)


__all__ = [
    "TracingConfig",
    "init_tracing",
    "get_tracer",
    "ensure_trace_id",
    "run_stage_span",
    "annotate_error",
]

