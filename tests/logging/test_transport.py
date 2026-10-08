import asyncio

import pytest

from mcp_agent.logging import logger  # noqa: F401 - initialize before transport
from mcp_agent.logging.events import Event
from mcp_agent.logging.listeners import LifecycleAwareListener
from mcp_agent.logging.transport import AsyncEventBus


class RecordingListener(LifecycleAwareListener):
    def __init__(self):
        self.messages = []

    async def start(self):
        self.received = asyncio.Event()
        await asyncio.sleep(0)

    async def handle_event(self, event):
        self.messages.append(event.message)
        self.received.set()


async def wait_until_idle(bus):
    # Synchronize with Queue.get rather than depending on a timed sleep.
    while not bus._queue._getters:
        await asyncio.sleep(0)


@pytest.mark.parametrize("new_loop", [False, True])
def test_event_bus_restarts(new_loop):
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)

    async def run(message):
        await bus.start()
        try:
            await bus.emit(Event(type="info", namespace="test", message=message))
            await asyncio.wait_for(listener.received.wait(), timeout=1)
            await asyncio.wait_for(bus._queue.join(), timeout=1)
        finally:
            await bus.stop()

    async def run_twice():
        await run("first run")
        await run("second run")

    if new_loop:
        asyncio.run(run("first run"))
        asyncio.run(run("second run"))
    else:
        asyncio.run(run_twice())

    assert listener.messages == ["first run", "second run"]


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_start_preserves_pending_events(concurrent):
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)

    if concurrent:
        await asyncio.gather(*(bus.start() for _ in range(3)))
    else:
        await bus.start()
    try:
        await bus.emit(Event(type="info", namespace="test", message="before restart"))
        if concurrent:
            await asyncio.gather(*(bus.start() for _ in range(3)))
        else:
            await bus.start()
        await asyncio.gather(
            *(
                bus.emit(Event(type="info", namespace="test", message=str(index)))
                for index in range(20)
            )
        )
        await asyncio.wait_for(bus._queue.join(), timeout=1)
    finally:
        await bus.stop()

    assert listener.messages == ["before restart", *(str(index) for index in range(20))]


@pytest.mark.asyncio
async def test_stop_cleans_up_idle_waiters():
    bus = AsyncEventBus()
    previous_tasks = asyncio.all_tasks()
    await bus.start()

    await asyncio.wait_for(wait_until_idle(bus), timeout=1)
    await bus.stop()

    assert asyncio.all_tasks() == previous_tasks


@pytest.mark.asyncio
async def test_stop_delivers_queued_events():
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)
    await bus.start()

    await asyncio.wait_for(wait_until_idle(bus), timeout=1)
    for index in range(3):
        await bus.emit(Event(type="info", namespace="test", message=str(index)))
    await bus.stop()

    assert listener.messages == ["0", "1", "2"]


def test_restart_preserves_events_emitted_while_stopped():
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)

    async def first_run():
        await bus.start()
        await bus.stop()
        await bus.emit(Event(type="info", namespace="test", message="between runs"))

    async def second_run():
        await bus.start()
        try:
            await asyncio.wait_for(listener.received.wait(), timeout=1)
            await asyncio.wait_for(bus._queue.join(), timeout=1)
        finally:
            await bus.stop()

    asyncio.run(first_run())
    asyncio.run(second_run())
    assert listener.messages == ["between runs"]


@pytest.mark.asyncio
async def test_explicit_start_preserves_auto_started_events():
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)

    await bus.emit(Event(type="info", namespace="test", message="before start"))
    await bus.start()
    try:
        await asyncio.wait_for(listener.received.wait(), timeout=1)
        await asyncio.wait_for(bus._queue.join(), timeout=1)
    finally:
        await bus.stop()

    assert listener.messages == ["before start"]


@pytest.mark.asyncio
async def test_cancellation_does_not_lose_a_ready_event():
    bus = AsyncEventBus()
    listener = RecordingListener()
    bus.add_listener("recording", listener)
    await bus.start()

    await asyncio.wait_for(wait_until_idle(bus), timeout=1)
    await bus.emit(Event(type="info", namespace="test", message="during cancellation"))
    # Let Queue.get dequeue the event before cancelling its parent worker.
    await asyncio.sleep(0)
    assert bus._queue.empty()
    assert listener.messages == []
    bus._task.cancel()
    await bus._task
    await bus.stop()

    assert listener.messages == ["during cancellation"]
    await asyncio.wait_for(bus._queue.join(), timeout=1)
