"""Runtime queue for human input requests served via the API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict

from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse


@dataclass
class _RequestEntry:
    request: HumanInputRequest
    future: asyncio.Future[HumanInputResponse] = field(default_factory=asyncio.Future)


class HumanInputRuntime:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending: Dict[str, _RequestEntry] = {}
        self._subscribers: set[asyncio.Queue[HumanInputRequest]] = set()

    async def add_request(self, request: HumanInputRequest) -> asyncio.Future[HumanInputResponse]:
        async with self._lock:
            entry = _RequestEntry(request=request)
            self._pending[request.request_id] = entry
            for subscriber in list(self._subscribers):
                try:
                    subscriber.put_nowait(request)
                except asyncio.QueueFull:
                    self._subscribers.discard(subscriber)
            return entry.future

    async def resolve(self, response: HumanInputResponse) -> bool:
        async with self._lock:
            entry = self._pending.pop(response.request_id, None)
            if entry is None:
                return False
            if not entry.future.done():
                entry.future.set_result(response)
            return True

    async def subscribe(self) -> asyncio.Queue[HumanInputRequest]:
        queue: asyncio.Queue[HumanInputRequest] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
            for entry in self._pending.values():
                queue.put_nowait(entry.request)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[HumanInputRequest]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def pending(self) -> list[HumanInputRequest]:
        async with self._lock:
            return [entry.request for entry in self._pending.values()]

    async def reset(self) -> None:
        async with self._lock:
            self._pending.clear()
            self._subscribers.clear()


human_input_runtime = HumanInputRuntime()

__all__ = ["HumanInputRuntime", "human_input_runtime"]
