import asyncio
import json

import pytest

from mcp_agent.runloop.events import BudgetSnapshot, EventBus, build_payload


@pytest.mark.asyncio
async def test_event_bus_publishes_structured_payload() -> None:
    bus = EventBus()
    queue = bus.subscribe()

    snapshot = BudgetSnapshot(llm_active_ms=1200, remaining_s=42.5)
    payload = build_payload(
        event="implementing_code",
        trace_id="trace-123",
        iteration=2,
        pack_hash="pack-abc",
        budget=snapshot,
        violation=False,
        note="hello",
    )

    await bus.publish(payload)
    raw = await queue.get()
    data = json.loads(raw)

    assert data["event"] == "implementing_code"
    assert data["trace_id"] == "trace-123"
    assert data["iteration"] == 2
    assert data["pack_hash"] == "pack-abc"
    assert data["budget"] == {"llm_active_ms": 1200, "remaining_s": 42.5}
    assert data["note"] == "hello"
    assert "ts" in data and data["ts"].endswith("Z")


@pytest.mark.asyncio
async def test_event_bus_close_notifies_subscribers() -> None:
    bus = EventBus()
    queue = bus.subscribe()

    await bus.close()
    message = await queue.get()
    assert message == "__EOF__"

    # New subscribers after closure receive terminal marker immediately.
    other_queue = bus.subscribe()
    assert await other_queue.get() == "__EOF__"
