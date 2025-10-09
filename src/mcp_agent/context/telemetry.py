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
            meter = metrics.get_meter("mcp_agent.context")
            self._hist = meter.create_histogram("mcp_assemble_duration_ms", unit="ms")
            self._ctr_overflow = meter.create_counter("mcp_budget_overflow_total")
            self._ctr_errors = meter.create_counter("mcp_assemble_errors_total")

    def record_duration_ms(self, value: float, attrs: Optional[Mapping[str, str]] = None):
        self._hist.record(value, attributes=attrs or {})

    def inc_overflow(self, inc: int = 1, attrs: Optional[Mapping[str, str]] = None):
        self._ctr_overflow.add(inc, attributes=attrs or {})

    def inc_errors(self, inc: int = 1, attrs: Optional[Mapping[str, str]] = None):
        self._ctr_errors.add(inc, attributes=attrs or {})


_meter_singleton: Optional[_Meter] = None


def meter() -> _Meter:
    global _meter_singleton
    if _meter_singleton is None:
        _meter_singleton = _Meter()
    return _meter_singleton
