from __future__ import annotations

from typing import Mapping, Optional

try:
    from opentelemetry import metrics
except Exception:  # pragma: no cover
    metrics = None  # type: ignore[assignment]


class _NoopInstrument:
    def record(self, *_args, **_kwargs):  # pragma: no cover
        return None

    def add(self, *_args, **_kwargs):  # pragma: no cover
        return None


class _Meter:
    def __init__(self):
        if metrics is None:  # pragma: no cover
            self._hist = _NoopInstrument()
            self._ctr_overflow = _NoopInstrument()
            self._ctr_errors = _NoopInstrument()
        else:
            meter = metrics.get_meter("context_assembly")
            self._hist = meter.create_histogram(
                "context_assembly_duration_ms",
                unit="ms",
                description="Distribution of context assembly durations",
            )
            self._ctr_overflow = meter.create_counter(
                "budget_overflow_count",
                unit="event",
                description="Count of budget overflow/prune events",
            )
            self._ctr_errors = meter.create_counter(
                "context_assembly_error_total",
                unit="event",
                description="Count of context assembly errors",
            )

    def record_duration_ms(self, value: float, attrs: Optional[Mapping[str, str]] = None):
        self._hist.record(value, attributes=attrs or {})

    def inc_overflow(self, inc: int = 1, attrs: Optional[Mapping[str, str]] = None):
        self._ctr_overflow.add(inc, attributes=attrs or {})

    def record_overflow(
        self,
        count: int,
        reason: str,
        attrs: Optional[Mapping[str, str]] = None,
    ) -> None:
        attributes = {"reason": reason, **(attrs or {})}
        self._ctr_overflow.add(count, attributes=attributes)

    def inc_errors(self, inc: int = 1, attrs: Optional[Mapping[str, str]] = None):
        self._ctr_errors.add(inc, attributes=attrs or {})


_meter_singleton: Optional[_Meter] = None


def meter() -> _Meter:
    global _meter_singleton
    if _meter_singleton is None:
        _meter_singleton = _Meter()
    return _meter_singleton


def record_overflow(
    count: int,
    reason: str,
    attrs: Optional[Mapping[str, str]] = None,
) -> None:
    meter().record_overflow(count, reason, attrs)


def setup_otel() -> None:
    """Best-effort OTEL metrics exporter setup.
    No-op if SDK not present. Uses default OTEL_* env vars.
    """
    try:  # pragma: no cover
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        # Minimal provider + reader using env-configured endpoint
        provider = MeterProvider(resource=Resource.create({}))
        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        provider._metric_readers.append(reader)  # type: ignore[attr-defined]
        # Bind provider
        from opentelemetry import metrics as _metrics  # type: ignore
        _metrics.set_meter_provider(provider)  # type: ignore
    except Exception:
        # Leave meter() as-is if OTEL not available
        return None
