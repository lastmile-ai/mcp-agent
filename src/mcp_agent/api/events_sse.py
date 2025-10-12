"""Server-sent event fan-out utilities for run lifecycle streams."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(slots=True)
class SSEMessage:
    """Internal representation of a single SSE payload."""

    event_id: int
    body: str


class RunEventStream:
    """Fan-out stream that replays lifecycle events to multiple subscribers."""

    _EOF: Tuple[int, str] = (-1, "__EOF__")

    def __init__(self) -> None:
        self._sequence = 0
        self._history: List[SSEMessage] = []
        self._queues: set[asyncio.Queue[Tuple[int, str]]] = set()
        self._closed = asyncio.Event()
        self._lock = asyncio.Lock()

    async def publish(
        self,
        *,
        run_id: str,
        state: str,
        timestamp: datetime | None = None,
        details: Dict[str, Any] | None = None,
    ) -> int:
        """Publish a lifecycle event to all subscribers."""

        ts = timestamp or datetime.now(timezone.utc)
        payload = {
            "run_id": run_id,
            "state": state,
            "timestamp": ts.strftime(ISO_FORMAT),
            "details": details or {},
        }
        body = json.dumps(payload)
        async with self._lock:
            if self._closed.is_set():
                return self._sequence
            self._sequence += 1
            message = SSEMessage(event_id=self._sequence, body=body)
            self._history.append(message)
            queues = list(self._queues)
        for queue in queues:
            try:
                queue.put_nowait((message.event_id, message.body))
            except asyncio.QueueFull:
                # Slow consumers can rely on replay using Last-Event-ID.
                pass
        return message.event_id

    def subscribe(self, last_event_id: Optional[int] = None) -> asyncio.Queue[Tuple[int, str]]:
        """Create a queue subscribed to this stream."""

        queue: asyncio.Queue[Tuple[int, str]] = asyncio.Queue()
        start_messages: Iterable[SSEMessage]
        if last_event_id is None:
            start_messages = self._history
        else:
            start_messages = [m for m in self._history if m.event_id > last_event_id]
        for message in start_messages:
            queue.put_nowait((message.event_id, message.body))
        if self._closed.is_set():
            queue.put_nowait(self._EOF)
        else:
            self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Tuple[int, str]]) -> None:
        """Remove a queue subscription."""

        self._queues.discard(queue)

    async def close(self) -> None:
        """Mark the stream closed and notify subscribers."""

        if self._closed.is_set():
            return
        self._closed.set()
        queues = list(self._queues)
        self._queues.clear()
        for queue in queues:
            try:
                queue.put_nowait(self._EOF)
            except asyncio.QueueFull:
                pass


__all__ = ["RunEventStream", "SSEMessage"]
