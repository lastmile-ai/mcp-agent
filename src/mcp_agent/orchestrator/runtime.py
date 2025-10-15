"""Runtime snapshot tracking for orchestrators."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from mcp_agent.models.orchestrator import (
    OrchestratorEvent,
    OrchestratorPlan,
    OrchestratorPlanNode,
    OrchestratorQueueItem,
    OrchestratorSnapshot,
    OrchestratorState,
    OrchestratorStatePatch,
)


@dataclass
class _OrchestratorInstance:
    state: OrchestratorState
    plan: OrchestratorPlan = field(default_factory=OrchestratorPlan)
    queue: list[OrchestratorQueueItem] = field(default_factory=list)
    event_counter: int = 0
    subscribers: set[asyncio.Queue[OrchestratorEvent]] = field(default_factory=set)


class OrchestratorRuntime:
    """Provides in-memory snapshots for orchestrator instances."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._instances: Dict[str, _OrchestratorInstance] = {}

    async def ensure(self, orchestrator_id: str) -> _OrchestratorInstance:
        async with self._lock:
            instance = self._instances.get(orchestrator_id)
            if instance is None:
                state = OrchestratorState(id=orchestrator_id)
                instance = _OrchestratorInstance(state=state)
                self._instances[orchestrator_id] = instance
            return instance

    async def get_snapshot(self, orchestrator_id: str) -> OrchestratorSnapshot:
        instance = await self.ensure(orchestrator_id)
        async with self._lock:
            return OrchestratorSnapshot(
                state=instance.state,
                queue=list(instance.queue),
                plan=instance.plan,
            )

    async def update_state(
        self, orchestrator_id: str, patch: OrchestratorStatePatch
    ) -> OrchestratorState:
        instance = await self.ensure(orchestrator_id)
        async with self._lock:
            update_payload = instance.state.model_dump()
            if patch.status is not None:
                update_payload["status"] = patch.status
            if patch.active_agents is not None:
                update_payload["active_agents"] = patch.active_agents
            if patch.budget_seconds_remaining is not None:
                update_payload["budget_seconds_remaining"] = patch.budget_seconds_remaining
            if patch.policy is not None:
                update_payload["policy"] = patch.policy
            if patch.memory is not None:
                update_payload["memory"] = patch.memory
            instance.state = OrchestratorState(**update_payload)
            event = self._create_event(instance, "state", instance.state.model_dump())
        await self._publish(instance, event)
        return instance.state

    async def set_plan(self, orchestrator_id: str, plan: OrchestratorPlan) -> OrchestratorPlan:
        instance = await self.ensure(orchestrator_id)
        async with self._lock:
            instance.plan = plan
            event = self._create_event(instance, "plan", plan.model_dump(mode="json"))
        await self._publish(instance, event)
        return plan

    async def set_queue(
        self, orchestrator_id: str, items: Iterable[OrchestratorQueueItem]
    ) -> list[OrchestratorQueueItem]:
        instance = await self.ensure(orchestrator_id)
        queue_items = list(items)
        async with self._lock:
            instance.queue = queue_items
            event = self._create_event(
                instance,
                "queue",
                [item.model_dump(mode="json") for item in queue_items],
            )
        await self._publish(instance, event)
        return queue_items

    async def subscribe(self, orchestrator_id: str) -> asyncio.Queue[OrchestratorEvent]:
        instance = await self.ensure(orchestrator_id)
        queue: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        async with self._lock:
            instance.subscribers.add(queue)
        snapshot = OrchestratorSnapshot(
            state=instance.state,
            queue=list(instance.queue),
            plan=instance.plan,
        )
        initial_event = self._create_event(
            instance,
            "snapshot",
            snapshot.model_dump(mode="json"),
        )
        await queue.put(initial_event)
        return queue

    async def unsubscribe(
        self, orchestrator_id: str, queue: asyncio.Queue[OrchestratorEvent]
    ) -> None:
        async with self._lock:
            instance = self._instances.get(orchestrator_id)
            if instance and queue in instance.subscribers:
                instance.subscribers.discard(queue)

    # ------------------------------------------------------------------
    def _create_event(
        self, instance: _OrchestratorInstance, event_type: str, payload: dict | list | None
    ) -> OrchestratorEvent:
        instance.event_counter += 1
        return OrchestratorEvent(
            id=instance.event_counter,
            type=event_type,
            payload={"data": payload} if payload is not None else {},
        )

    async def _publish(
        self, instance: _OrchestratorInstance, event: OrchestratorEvent
    ) -> None:
        to_remove: list[asyncio.Queue[OrchestratorEvent]] = []
        for queue in list(instance.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                to_remove.append(queue)
        if to_remove:
            async with self._lock:
                for queue in to_remove:
                    instance.subscribers.discard(queue)


orchestrator_runtime = OrchestratorRuntime()

__all__ = ["OrchestratorRuntime", "orchestrator_runtime"]
