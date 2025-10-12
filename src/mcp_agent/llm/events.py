"""Helpers for emitting LLM lifecycle events onto the existing SSE fan-out."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable

from mcp_agent.telemetry import llm_sse_consumer_count


class LLMEventFanout:
    """Thread-safe fan-out of serialized LLM events to multiple subscribers."""

    def __init__(self, *, max_queue_size: int = 256) -> None:
        self._max_queue_size = max_queue_size
        self._queues: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    async def publish(self, payload: str) -> None:
        """Best-effort publish to all active subscribers."""

        async with self._lock:
            if self._closed:
                return
            stale: list[asyncio.Queue[str]] = []
            for queue in list(self._queues):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    stale.append(queue)
                except Exception:
                    stale.append(queue)
            for queue in stale:
                self._queues.discard(queue)
                llm_sse_consumer_count.add(-1, {"stream": "llm"})

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            for queue in list(self._queues):
                try:
                    queue.put_nowait("__EOF__")
                except Exception:
                    pass
            for _ in self._queues:
                llm_sse_consumer_count.add(-1, {"stream": "llm"})
            self._queues.clear()

    async def subscribe(self) -> asyncio.Queue[str]:
        """Create a new subscriber queue with historical replay disabled."""

        queue: asyncio.Queue[str] = asyncio.Queue(self._max_queue_size)
        async with self._lock:
            if self._closed:
                queue.put_nowait("__EOF__")
                return queue
            self._queues.add(queue)
            llm_sse_consumer_count.add(1, {"stream": "llm"})
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            if queue in self._queues:
                self._queues.discard(queue)
                llm_sse_consumer_count.add(-1, {"stream": "llm"})

    async def snapshot(self) -> list[asyncio.Queue[str]]:
        async with self._lock:
            return list(self._queues)


async def emit_llm_event(state: Any, run_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Emit a structured LLM event onto the shared public API SSE queues.

    Parameters
    ----------
    state:
        The public API state that owns the SSE queues. The object must expose
        either an ``llm_streams`` mapping of run IDs to :class:`LLMEventFanout`
        instances or a legacy ``queues`` mapping for backward compatibility.
    run_id:
        Identifier of the run associated with the event.
    event_type:
        Fully qualified event type (e.g. ``"llm/starting"``).
    data:
        Additional event payload. A ``run_id`` attribute is automatically
        included so consumers can always correlate the event without reading
        the envelope.
    """

    if state is None or not run_id:
        return

    payload = {"event": "llm", "type": event_type, "run_id": run_id, **data}
    serialized = json.dumps(payload)

    delivered = False

    fanouts: Dict[str, LLMEventFanout] | None = getattr(state, "llm_streams", None)
    if fanouts:
        fanout = fanouts.get(run_id)
        if fanout is not None:
            await fanout.publish(serialized)
            delivered = True

    queues = getattr(state, "queues", None)
    consumers: Iterable[asyncio.Queue[str]] = []
    if queues:
        consumers = list(queues.get(run_id, []))
        delivered = delivered or bool(consumers)
    if not delivered:
        return

    async def _put(q: "asyncio.Queue[str]") -> None:
        try:
            await q.put(serialized)
        except Exception:
            # Ignore queue delivery failures – losing a single consumer must
            # not abort the entire gateway flow.
            pass

    if consumers:
        await asyncio.gather(*(_put(queue) for queue in consumers))
