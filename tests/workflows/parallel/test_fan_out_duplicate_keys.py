from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from mcp_agent.core.context import Context
from mcp_agent.executor.executor import AsyncioExecutor
from mcp_agent.workflows.parallel.fan_out import FanOut


class Result(BaseModel):
    value: str


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["generate", "generate_str", "generate_structured"])
async def test_duplicate_worker_names_fail_before_execution(method):
    executor = AsyncioExecutor()
    executor.execute_many = AsyncMock()

    def worker(message):
        return [message]

    fan = FanOut(functions=[worker], context=Context(executor=executor))
    fan.functions.append(worker)
    kwargs = {"response_model": Result} if method == "generate_structured" else {}
    with pytest.raises(ValueError, match="worker"):
        await getattr(fan, method)("hello", **kwargs)
    executor.execute_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_unique_workers_keep_results():
    def north(message):
        return [message + ":north"]

    def south(message):
        return [message + ":south"]

    fan = FanOut(functions=[north, south], context=Context(executor=AsyncioExecutor()))
    assert await fan.generate("stock") == {
        "north": ["stock:north"],
        "south": ["stock:south"],
    }
