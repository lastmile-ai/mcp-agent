"""Telemetry primitives for tracking run lifecycle state transitions."""

from __future__ import annotations

from typing import Mapping

from opentelemetry import metrics

_meter = metrics.get_meter("mcp-agent.run.lifecycle")

state_transition_counter = _meter.create_counter(
    "run_state_transitions_total",
    unit="1",
    description="Total number of run lifecycle state transitions.",
)

state_duration_histogram = _meter.create_histogram(
    "run_state_duration_seconds",
    unit="s",
    description="Observed time spent in individual run lifecycle states.",
)


def record_transition(
    *,
    run_id: str,
    previous_state: str | None,
    next_state: str,
    duration_s: float | None,
    attributes: Mapping[str, str] | None = None,
) -> None:
    """Record telemetry for a state transition."""

    attrs: dict[str, str] = {"run_id": run_id, "to": next_state}
    if previous_state:
        attrs["from"] = previous_state
    if attributes:
        attrs.update(attributes)
    state_transition_counter.add(1, attrs)
    if previous_state and duration_s is not None:
        duration_attrs = {"run_id": run_id, "state": previous_state}
        if attributes:
            duration_attrs.update(attributes)
        state_duration_histogram.record(duration_s, duration_attrs)


__all__ = [
    "record_transition",
    "state_transition_counter",
    "state_duration_histogram",
]
