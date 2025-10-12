import asyncio
import json

import pytest

from mcp_agent.api.events_sse import RunEventStream
from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.controller import RunConfig, RunController
from mcp_agent.runloop.lifecyclestate import RunLifecycle, RunState


@pytest.mark.asyncio
async def test_run_controller_emits_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0.0, 0.01, 0.02, 0.05])

    def fake_time() -> float:
        return next(times)

    monkeypatch.setattr("mcp_agent.budget.llm_budget.time.time", fake_time)

    stream = RunEventStream()
    lifecycle = RunLifecycle(run_id="run-1", stream=stream)
    await lifecycle.transition_to(RunState.QUEUED, details={"trace_id": "trace"})
    queue = stream.subscribe()
    controller = RunController(
        config=RunConfig(trace_id="trace", iteration_count=2, pack_hash="pack"),
        lifecycle=lifecycle,
        cancel_event=asyncio.Event(),
        llm_budget=LLMBudget(),
    )

    task = asyncio.create_task(controller.run())

    events: list[dict] = []
    while True:
        event_id, message = await queue.get()
        if event_id == -1:
            break
        events.append(json.loads(message))

    await task

    states = [event["state"] for event in events]
    assert states == [
        RunState.QUEUED.value,
        RunState.PREPARING.value,
        RunState.ASSEMBLING.value,
        RunState.PROMPTING.value,
        RunState.APPLYING.value,
        RunState.TESTING.value,
        RunState.PROMPTING.value,
        RunState.APPLYING.value,
        RunState.TESTING.value,
        RunState.GREEN.value,
    ]

    prompting_events = [event for event in events if event["state"] == RunState.PROMPTING.value]
    assert prompting_events[0]["details"]["budget"]["llm_active_ms"] == 0
    assert prompting_events[1]["details"]["budget"]["llm_active_ms"] == 10
    applying_events = [event for event in events if event["state"] == RunState.APPLYING.value]
    assert applying_events[0]["details"]["budget"]["llm_active_ms"] == 10
    assert applying_events[1]["details"]["budget"]["llm_active_ms"] == 40
    assert events[-1]["details"]["iterations"] == 2
