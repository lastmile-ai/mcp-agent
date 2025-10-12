"""Very small asynchronous run loop controller."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.events import BudgetSnapshot
from mcp_agent.runloop.lifecyclestate import RunLifecycle, RunState


@dataclass
class RunConfig:
    trace_id: str
    iteration_count: int
    pack_hash: str | None = None
    feature_spec: Dict[str, Any] | None = None
    approved_budget_s: int | None = None
    caps: Dict[str, Any] | None = None


class RunCanceled(Exception):
    """Raised when a run is canceled mid-flight."""


class RunController:
    def __init__(
        self,
        *,
        config: RunConfig,
        lifecycle: RunLifecycle,
        cancel_event: asyncio.Event | None = None,
        llm_budget: LLMBudget | None = None,
        feature_spec: Any | None = None,
        approved_budget_s: int | None = None,
    ) -> None:
        self._config = config
        self._lifecycle = lifecycle
        self._cancel_event = cancel_event or asyncio.Event()
        self._budget = llm_budget or LLMBudget()
        self._feature_spec = feature_spec or config.feature_spec
        self._approved_budget_s = approved_budget_s or config.approved_budget_s
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        try:
            await self._lifecycle.transition_to(
                RunState.PREPARING,
                details={
                    "trace_id": self._config.trace_id,
                    "pack_hash": self._config.pack_hash,
                    "approved_budget_s": self._approved_budget_s,
                },
            )
            await self._ensure_not_canceled()

            await self._lifecycle.transition_to(
                RunState.ASSEMBLING,
                details={
                    "has_feature_spec": bool(self._feature_spec),
                    "caps": self._config.caps or {},
                },
            )
            await self._ensure_not_canceled()

            for iteration in range(1, self._config.iteration_count + 1):
                await self._lifecycle.transition_to(
                    RunState.PROMPTING,
                    details={
                        "iteration": iteration,
                        "budget": self._snapshot().as_dict(),
                    },
                )
                await self._ensure_not_canceled()

                async with self._track_llm():
                    await asyncio.sleep(0)

                await self._lifecycle.transition_to(
                    RunState.APPLYING,
                    details={
                        "iteration": iteration,
                        "budget": self._snapshot().as_dict(),
                    },
                )
                await self._ensure_not_canceled()

                await asyncio.sleep(0)

                await self._lifecycle.transition_to(
                    RunState.TESTING,
                    details={
                        "iteration": iteration,
                        "budget": self._snapshot().as_dict(),
                    },
                )
                await self._ensure_not_canceled()

            await self._ensure_not_canceled()
            await self._lifecycle.transition_to(
                RunState.GREEN,
                details={"iterations": self._config.iteration_count},
            )
        except RunCanceled:
            raise
        finally:
            self._stopped.set()

    async def wait_closed(self) -> None:
        await self._stopped.wait()

    def _snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            llm_active_ms=self._budget.active_ms,
            remaining_s=self._budget.remaining_seconds(),
        )

    async def _ensure_not_canceled(self) -> None:
        if self._cancel_event.is_set():
            if not self._lifecycle.is_terminal():
                await self._lifecycle.transition_to(
                    RunState.CANCELED,
                    details={"at": self._lifecycle.state.value if self._lifecycle.state else None},
                )
            raise RunCanceled()

    @asynccontextmanager
    async def _track_llm(self):
        self._budget.start()
        try:
            yield
        finally:
            self._budget.stop()


__all__ = ["RunCanceled", "RunController", "RunConfig"]
