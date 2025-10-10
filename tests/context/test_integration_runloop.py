import asyncio
import json

import pytest

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.controller import RunConfig, RunController
from mcp_agent.runloop.events import EventBus


@pytest.mark.asyncio
async def test_run_controller_emits_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0.0, 0.01, 0.02, 0.05])

    def fake_time() -> float:
        return next(times)

    monkeypatch.setattr("mcp_agent.budget.llm_budget.time.time", fake_time)

    bus = EventBus()
    queue = bus.subscribe()
    controller = RunController(
        config=RunConfig(trace_id="trace", iteration_count=2, pack_hash="pack"),
        event_bus=bus,
        llm_budget=LLMBudget(),
    )

    task = asyncio.create_task(controller.run())

    events: list[dict] = []
    while True:
        message = await queue.get()
        if message == "__EOF__":
            break
        events.append(json.loads(message))

    await task

    assert [event["event"] for event in events] == [
        "initializing_run",
        "implementing_code",
        "implementing_code",
        "finished_green",
    ]

    assert events[0]["budget"] == {"llm_active_ms": 0, "remaining_s": None}
    assert events[1]["budget"]["llm_active_ms"] == 10
    assert events[2]["budget"]["llm_active_ms"] == 40
    assert events[3]["budget"]["llm_active_ms"] == 40
    assert all(event["trace_id"] == "trace" for event in events)
    assert all(event["pack_hash"] == "pack" for event in events)
