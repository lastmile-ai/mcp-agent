import asyncio
from contextlib import asynccontextmanager
from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

from mcp_agent.logging import token_progress_display

TIMEOUT = 5


class ControlledCounter:
    """Provide explicit barriers just before watch returns and unwatch removes."""

    def __init__(self):
        self.active = set()
        self.watch_started = asyncio.Queue()
        self.watch_gates = {}
        self.unwatch_started = asyncio.Event()
        self.unwatch_gate = asyncio.Event()
        self.unwatch_gate.set()
        self.next_id = 1

    async def get_app_node(self):
        return None

    async def watch(self, **kwargs):
        watch_id = str(self.next_id)
        self.next_id += 1
        self.active.add(watch_id)
        self.watch_started.put_nowait(watch_id)
        if watch_id in self.watch_gates:
            await self.watch_gates[watch_id].wait()
        return watch_id

    async def unwatch(self, watch_id):
        self.unwatch_started.set()
        await self.unwatch_gate.wait()
        self.active.discard(watch_id)


class DisplaySession:
    def __init__(self, monkeypatch):
        self.counter = ControlledCounter()
        self.tasks = []
        self.display = token_progress_display.TokenProgressDisplay(
            self.counter, Console(file=StringIO())
        )

        def track(coroutine):
            task = asyncio.create_task(coroutine)
            self.tasks.append(task)
            return task

        # Capture only display work; do not change asyncio for pytest or Rich.
        monkeypatch.setattr(
            token_progress_display,
            "asyncio",
            SimpleNamespace(
                create_task=track, get_running_loop=asyncio.get_running_loop
            ),
        )

    async def watch_started(self, expected_id):
        assert (
            await asyncio.wait_for(self.counter.watch_started.get(), TIMEOUT)
            == expected_id
        )

    async def join(self, *tasks):
        await asyncio.wait_for(asyncio.gather(*(tasks or self.tasks)), TIMEOUT)

    async def cleanup(self):
        for gate in self.counter.watch_gates.values():
            gate.set()
        self.counter.unwatch_gate.set()
        try:
            await self.join()
        finally:
            self.display.stop()
            try:
                await self.join()
            finally:
                # Red runs can leave untracked subscriptions in this test double.
                self.counter.active.clear()

    @asynccontextmanager
    async def managed(self):
        try:
            yield
        finally:
            await self.cleanup()


@pytest.fixture
def session(monkeypatch):
    return DisplaySession(monkeypatch)


@pytest.mark.asyncio
async def test_stop_reclaims_watch_when_id_arrives_late(session):
    async with session.managed():
        session.counter.watch_gates["1"] = gate = asyncio.Event()
        session.display.start()
        await session.watch_started("1")
        assert session.display.stop() is None
        gate.set()
        await session.join()
        assert session.counter.active == set()


@pytest.mark.asyncio
async def test_previous_stop_does_not_remove_restarted_watch(session):
    async with session.managed():
        session.display.start()
        await session.watch_started("1")
        await session.join()
        session.counter.unwatch_gate.clear()
        session.display.stop()
        await asyncio.wait_for(session.counter.unwatch_started.wait(), TIMEOUT)

        session.display.start()
        await session.watch_started("2")
        await session.join(session.tasks[-1])
        session.counter.unwatch_gate.set()
        await session.join()
        assert session.counter.active == {"2"}

        session.display.stop()
        await session.join()
        assert session.counter.active == set()


@pytest.mark.asyncio
async def test_previous_registration_does_not_join_restarted_display(session):
    async with session.managed():
        session.counter.watch_gates["1"] = gate = asyncio.Event()
        session.display.start()
        await session.watch_started("1")
        session.display.stop()

        session.display.start()
        await session.watch_started("2")
        await session.join(session.tasks[-1])
        gate.set()
        await session.join()
        assert session.counter.active == {"2"}


def test_start_without_running_loop_can_be_retried(session):
    async def retry():
        async with session.managed():
            session.display.start()
            await session.watch_started("1")
            await session.join()
            assert session.counter.active == {"1"}

    try:
        with pytest.raises(RuntimeError, match="no running event loop"):
            session.display.start()
        asyncio.run(retry())
    finally:
        session.display._progress.stop()


def test_stop_without_running_loop_can_be_retried(session):
    async def start():
        session.display.start()
        await session.watch_started("1")
        await session.join()

    async def retry():
        session.display.stop()
        await session.join()
        assert session.counter.active == set()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(start())
        with pytest.raises(RuntimeError, match="no running event loop"):
            session.display.stop()
        loop.run_until_complete(retry())
    finally:
        try:
            loop.run_until_complete(session.cleanup())
        finally:
            loop.close()


def test_stop_before_start_does_not_require_a_running_loop(session):
    assert session.display.stop() is None
    assert not session.tasks
