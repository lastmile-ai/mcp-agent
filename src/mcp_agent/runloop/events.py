"""Utilities for emitting structured run loop events.

This module defines a tiny event bus that the public API can use to fan out
server-sent events (SSE) to multiple consumers.  The real system described in
our product brief includes a rich set of event types.  For the purposes of the
open source agent we model a greatly simplified subset that still captures the
shape of the wire protocol: every payload includes the trace identifier, the
current iteration number, a pack hash (when available) and budget accounting
information.

The helpers provided here are intentionally lightweight so they can be used in
unit tests without spinning up background tasks.  ``EventBus`` simply stores a
set of asyncio queues.  Publishing is best-effort; slow consumers only affect
their own queue.  ``build_payload`` centralises the schema we expose over SSE so
that other modules do not have to duplicate the boilerplate fields.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Set

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(slots=True)
class BudgetSnapshot:
    """Represents the LLM budget state at the time of an event."""

    llm_active_ms: int = 0
    remaining_s: float | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {"llm_active_ms": self.llm_active_ms, "remaining_s": self.remaining_s}


@dataclass(slots=True)
class EventPayload:
    """Structured payload sent over SSE."""

    event: str
    trace_id: str
    iteration: int
    pack_hash: str | None = None
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> str:
        body = {
            "event": self.event,
            "trace_id": self.trace_id,
            "iteration": self.iteration,
            "pack_hash": self.pack_hash,
            "budget": self.budget.as_dict(),
            "ts": datetime.now(timezone.utc).strftime(ISO_FORMAT),
        }
        body.update(self.extra)
        return json.dumps(body)


def build_payload(
    *,
    event: str,
    trace_id: str,
    iteration: int,
    pack_hash: str | None,
    budget: BudgetSnapshot | None = None,
    **extra: Any,
) -> EventPayload:
    """Create a new :class:`EventPayload` with the schema required by the API."""

    snapshot = budget or BudgetSnapshot()
    return EventPayload(
        event=event,
        trace_id=trace_id,
        iteration=iteration,
        pack_hash=pack_hash,
        budget=snapshot,
        extra=dict(extra),
    )


FEATURE_EVENT_NAMES = [
    "feature_drafting",
    "feature_estimated",
    "awaiting_budget_confirmation",
    "budget_confirmed",
    "feature_cancelled",
    "starting_implementation",
]

class EventBus:
    """Simple fan-out event bus backed by asyncio queues."""

    def __init__(self) -> None:
        self._queues: Set[asyncio.Queue[str]] = set()
        self._closed = asyncio.Event()
        self._history: list[str] = []

    def subscribe(self) -> asyncio.Queue[str]:
        """Create a new queue subscriber."""

        q: asyncio.Queue[str] = asyncio.Queue()
        for message in self._history:
            q.put_nowait(message)
        if self._closed.is_set():
            q.put_nowait("__EOF__")
        else:
            self._queues.add(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._queues.discard(queue)

    async def publish(self, payload: EventPayload) -> None:
        if self._closed.is_set():
            return
        message = payload.as_json()
        self._history.append(message)
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Drop messages for slow consumers; they can rely on terminal events.
                pass

    async def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        for queue in list(self._queues):
            try:
                queue.put_nowait("__EOF__")
            except asyncio.QueueFull:
                pass
        self._queues.clear()


__all__ = [
    "BudgetSnapshot",
    "EventPayload",
    "EventBus",
    "FEATURE_EVENT_NAMES",
    "build_payload",
]
