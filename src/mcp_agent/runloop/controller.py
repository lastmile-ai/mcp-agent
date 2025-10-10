"""Very small asynchronous run loop controller.

The production controller coordinates targeted checks, patch application and a
repair workflow.  Implementing the full behaviour is outside the scope of the
open source example, but exposing a cooperative coroutine makes it easier to
write integration tests.  The controller below emits a couple of well-known
states before marking the run finished.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.events import BudgetSnapshot, EventBus, build_payload


@dataclass
class RunConfig:
    trace_id: str
    iteration_count: int
    pack_hash: str | None = None


class RunController:
    def __init__(
        self,
        *,
        config: RunConfig,
        event_bus: EventBus,
        llm_budget: LLMBudget | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._budget = llm_budget or LLMBudget()
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        await self._event_bus.publish(
            build_payload(
                event="initializing_run",
                trace_id=self._config.trace_id,
                iteration=0,
                pack_hash=self._config.pack_hash,
                budget=self._snapshot(),
            )
        )
        for iteration in range(1, self._config.iteration_count + 1):
            async with self._track_llm():
                await asyncio.sleep(0)
            await self._event_bus.publish(
                build_payload(
                    event="implementing_code",
                    trace_id=self._config.trace_id,
                    iteration=iteration,
                    pack_hash=self._config.pack_hash,
                    budget=self._snapshot(),
                )
            )
        await self._event_bus.publish(
            build_payload(
                event="finished_green",
                trace_id=self._config.trace_id,
                iteration=self._config.iteration_count,
                pack_hash=self._config.pack_hash,
                budget=self._snapshot(),
            )
        )
        await self._event_bus.close()
        self._stopped.set()

    async def wait_closed(self) -> None:
        await self._stopped.wait()

    def _snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            llm_active_ms=self._budget.active_ms,
            remaining_s=self._budget.remaining_seconds(),
        )

    @asynccontextmanager
    async def _track_llm(self):
        self._budget.start()
        try:
            yield
        finally:
            self._budget.stop()


__all__ = ["RunController", "RunConfig"]
