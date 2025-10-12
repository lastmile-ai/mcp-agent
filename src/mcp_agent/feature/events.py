"""Feature intake SSE helpers."""

from __future__ import annotations

from typing import Any

from mcp_agent.runloop.events import EventBus, build_payload

from .models import FeatureDraft


async def emit_event(bus: EventBus, feature: FeatureDraft, *, name: str, **extra: Any) -> None:
    payload = build_payload(
        event=name,
        trace_id=feature.trace_id,
        iteration=0,
        pack_hash=None,
        feature_id=feature.feature_id,
        state=feature.state.value,
        **extra,
    )
    await bus.publish(payload)


async def emit_drafting(bus: EventBus, feature: FeatureDraft) -> None:
    await emit_event(bus, feature, name="feature_drafting", messages=feature.transcript())


async def emit_estimated(bus: EventBus, feature: FeatureDraft) -> None:
    estimate = feature.estimate.as_dict() if feature.estimate else None
    await emit_event(bus, feature, name="feature_estimated", estimate=estimate)


async def emit_awaiting_confirmation(bus: EventBus, feature: FeatureDraft) -> None:
    await emit_event(bus, feature, name="awaiting_budget_confirmation")


async def emit_budget_confirmed(bus: EventBus, feature: FeatureDraft) -> None:
    decision = feature.decision.as_dict() if feature.decision else None
    await emit_event(bus, feature, name="budget_confirmed", decision=decision)


async def emit_cancelled(bus: EventBus, feature: FeatureDraft) -> None:
    await emit_event(bus, feature, name="feature_cancelled")


async def emit_starting_implementation(bus: EventBus, feature: FeatureDraft, run_id: str) -> None:
    await emit_event(bus, feature, name="starting_implementation", run_id=run_id)


__all__ = [
    "emit_awaiting_confirmation",
    "emit_budget_confirmed",
    "emit_cancelled",
    "emit_drafting",
    "emit_estimated",
    "emit_event",
    "emit_starting_implementation",
]
