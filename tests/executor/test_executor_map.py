from types import SimpleNamespace

import pytest

from mcp_agent.executor.executor import AsyncioExecutor, ExecutorConfig
from mcp_agent.tracing.telemetry import telemetry


@pytest.fixture(params=[None, 2], ids=["unbounded", "bounded"])
def executor(request):
    config = ExecutorConfig(max_concurrent_activities=request.param)
    with telemetry.use_context(SimpleNamespace(tracer=None)):
        yield AsyncioExecutor(config=config)


@pytest.mark.asyncio
@pytest.mark.parametrize("async_func", [False, True], ids=["sync", "async"])
async def test_map_preserves_list_results(executor, async_func):
    inputs = [[1, 2], [], [[3], 4]]

    if async_func:

        async def identity(item):
            return item

    else:

        def identity(item):
            return item

    assert await executor.map(identity, inputs) == inputs


@pytest.mark.asyncio
async def test_map_preserves_result_and_exception_order(executor):
    error = ValueError("task failed")

    async def task(item):
        if item == "fail":
            raise error
        return item

    assert await executor.map(task, [1, "fail", (2, 3), {"value": 4}]) == [
        1,
        error,
        (2, 3),
        {"value": 4},
    ]


@pytest.mark.asyncio
async def test_map_empty_inputs(executor):
    assert await executor.map(lambda item: item, []) == []
