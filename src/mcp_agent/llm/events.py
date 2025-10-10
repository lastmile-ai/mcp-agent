"""Helpers for emitting LLM lifecycle events onto the existing SSE queues."""

from __future__ import annotations

import asyncio
import json
from typing import Any


async def emit_llm_event(state: Any, run_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Emit a structured LLM event onto the shared public API SSE queues.

    Parameters
    ----------
    state:
        The public API state that owns the SSE queues. The object must expose
        a ``queues`` attribute mapping run IDs to an iterable of
        :class:`asyncio.Queue` instances.
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

    queues = getattr(state, "queues", None)
    if not queues:
        return

    consumers = list(queues.get(run_id, []))
    if not consumers:
        return

    payload = {"event": "llm", "type": event_type, "run_id": run_id, **data}
    serialized = json.dumps(payload)

    async def _put(q: "asyncio.Queue[str]") -> None:
        try:
            await q.put(serialized)
        except Exception:
            # Ignore queue delivery failures – losing a single consumer must
            # not abort the entire gateway flow.
            pass

    await asyncio.gather(*(_put(queue) for queue in consumers))
