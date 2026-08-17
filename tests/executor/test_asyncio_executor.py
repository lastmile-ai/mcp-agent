import pytest

from mcp_agent.executor.executor import AsyncioExecutor


async def _add(a, b, offset=0):
    return a + b + offset


@pytest.mark.asyncio
async def test_execute_forwards_positional_and_keyword_args():
    executor = AsyncioExecutor()
    assert await executor.execute(_add, 1, 2, offset=3) == 6


@pytest.mark.asyncio
async def test_execute_many_forwards_positional_and_keyword_args():
    executor = AsyncioExecutor()
    results = await executor.execute_many([_add, _add], 1, 2, offset=3)
    assert results == [6, 6]


@pytest.mark.asyncio
async def test_execute_streaming_forwards_positional_and_keyword_args():
    executor = AsyncioExecutor()
    results = [
        result async for result in executor.execute_streaming([_add], 1, 2, offset=3)
    ]
    assert results == [6]
