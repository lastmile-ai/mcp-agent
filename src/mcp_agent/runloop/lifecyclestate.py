"""Run lifecycle state machine and helpers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from typing import Any, Dict, Optional

from mcp_agent.api.events_sse import RunEventStream
from mcp_agent.telemetry.run import record_transition

logger = logging.getLogger(__name__)


class RunState(Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    ASSEMBLING = "assembling"
    PROMPTING = "prompting"
    APPLYING = "applying"
    TESTING = "testing"
    REPAIRING = "repairing"
    GREEN = "green"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_STATES = {RunState.GREEN, RunState.FAILED, RunState.CANCELED}

_ALLOWED_TRANSITIONS: Dict[Optional[RunState], set[RunState]] = {
    None: {RunState.QUEUED},
    RunState.QUEUED: {RunState.PREPARING, RunState.CANCELED},
    RunState.PREPARING: {RunState.ASSEMBLING, RunState.CANCELED, RunState.FAILED},
    RunState.ASSEMBLING: {RunState.PROMPTING, RunState.CANCELED, RunState.FAILED},
    RunState.PROMPTING: {RunState.APPLYING, RunState.CANCELED, RunState.FAILED},
    RunState.APPLYING: {
        RunState.TESTING,
        RunState.REPAIRING,
        RunState.CANCELED,
        RunState.FAILED,
    },
    RunState.TESTING: {
        RunState.GREEN,
        RunState.REPAIRING,
        RunState.CANCELED,
        RunState.FAILED,
        RunState.PROMPTING,
    },
    RunState.REPAIRING: {
        RunState.APPLYING,
        RunState.CANCELED,
        RunState.FAILED,
    },
    RunState.GREEN: set(),
    RunState.FAILED: set(),
    RunState.CANCELED: set(),
}


@dataclass
class RunLifecycle:
    """State machine tracking a run's lifecycle."""

    run_id: str
    stream: RunEventStream
    _state: Optional[RunState] = field(default=None, init=False)
    _entered_at: float = field(default_factory=perf_counter, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> Optional[RunState]:
        return self._state

    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    async def transition_to(
        self,
        next_state: RunState,
        *,
        details: Dict[str, Any] | None = None,
    ) -> RunState:
        """Transition to the next state, emitting telemetry and SSE events."""

        if not isinstance(next_state, RunState):
            raise TypeError("next_state must be a RunState")

        async with self._lock:
            previous = self._state
            if previous in TERMINAL_STATES and previous != next_state:
                raise RuntimeError(
                    f"Run {self.run_id} already finished in {previous.value}; cannot transition to {next_state.value}."
                )
            allowed = _ALLOWED_TRANSITIONS.get(previous)
            if allowed is None or next_state not in allowed:
                prev = previous.value if previous else "<unset>"
                raise RuntimeError(
                    f"Illegal lifecycle transition {prev} -> {next_state.value} for run {self.run_id}."
                )
            now = perf_counter()
            duration = now - self._entered_at if previous is not None else None
            self._state = next_state
            self._entered_at = now

        logger.info(
            "run.lifecycle.transition",
            extra={"run_id": self.run_id, "from": previous.name if previous else None, "to": next_state.name},
        )

        timestamp = datetime.now(timezone.utc)
        await self.stream.publish(
            run_id=self.run_id,
            state=next_state.value,
            timestamp=timestamp,
            details=details or {},
        )
        record_transition(
            run_id=self.run_id,
            previous_state=previous.value if previous else None,
            next_state=next_state.value,
            duration_s=duration,
        )

        if next_state in TERMINAL_STATES:
            await self.stream.close()

        return next_state


__all__ = ["RunLifecycle", "RunState", "TERMINAL_STATES"]
