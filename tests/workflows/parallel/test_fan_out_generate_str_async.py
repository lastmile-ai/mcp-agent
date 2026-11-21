"""Local FanOut string projection with the real asyncio executor."""

import asyncio
import threading
from contextvars import ContextVar

import pytest
import pytest_asyncio

from mcp_agent.core.context import Context
from mcp_agent.executor.executor import AsyncioExecutor
from mcp_agent.logging.transport import AsyncEventBus
from mcp_agent.workflows.parallel.fan_out import FanOut


@pytest_asyncio.fixture
async def context():
    yield Context(executor=AsyncioExecutor())
    await AsyncEventBus.get().stop()


@pytest.mark.asyncio
async def test_plain_async_worker_is_awaited_and_stringified(context):
    calls = []
    token = ContextVar("test_token")
    token.set("caller")
    loop = asyncio.get_running_loop()

    async def worker(message):
        calls.append((message, token.get(), asyncio.get_running_loop()))
        return [f"north:{message}"]

    fan = FanOut(functions=[worker], context=context)
    generic = await asyncio.wait_for(fan.generate("stock"), 4)
    assert generic == {"worker": ["north:stock"]}
    assert calls == [("stock", "caller", loop)]
    calls.clear()

    projected = await asyncio.wait_for(fan.generate_str("stock"), 4)
    assert calls == [("stock", "caller", loop)], projected
    assert projected == {"worker": "['north:stock']"}


@pytest.mark.asyncio
async def test_sync_worker_creating_coroutine_stays_offloaded_then_is_awaited(context):
    caller_thread = threading.get_ident()
    loop = asyncio.get_running_loop()
    seen = []

    async def finish(message):
        seen.append(("awaited", asyncio.get_running_loop()))
        return {"text": message}

    def worker(message):
        seen.append(("dispatch", threading.get_ident()))
        return finish(message)

    fan = FanOut(functions=[worker], context=context)
    projected = await asyncio.wait_for(fan.generate_str("stock"), 4)
    assert len(seen) == 2, (seen, projected)
    assert seen[0][0] == "dispatch" and seen[0][1] != caller_thread
    assert seen[1] == ("awaited", loop)
    assert projected == {"worker": "{'text': 'stock'}"}


@pytest.mark.asyncio
async def test_sync_worker_and_string_conversion_remain_offloaded(context):
    caller_thread = threading.get_ident()
    seen = []

    class Value:
        def __str__(self):
            seen.append(("str", threading.get_ident()))
            return "unchanged"

    def worker(message):
        seen.append(("call", threading.get_ident()))
        return Value()

    fan = FanOut(functions=[worker], context=context)
    assert await asyncio.wait_for(fan.generate_str("stock"), 4) == {
        "worker": "unchanged"
    }
    assert len(seen) == 2
    assert [phase for phase, _ in seen] == ["call", "str"]
    assert seen[0][1] == seen[1][1] and seen[0][1] != caller_thread


@pytest.mark.asyncio
@pytest.mark.parametrize("async_worker", [False, True])
async def test_worker_exception_is_kept_as_the_same_result_entry(context, async_worker):
    error = ValueError("local worker failure")

    if async_worker:

        async def worker(message):
            raise error

    else:

        def worker(message):
            raise error

    fan = FanOut(functions=[worker], context=context)
    projected = await asyncio.wait_for(fan.generate_str("stock"), 4)
    assert projected["worker"] is error
