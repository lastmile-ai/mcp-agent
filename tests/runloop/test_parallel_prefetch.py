import pytest

from mcp_agent.runloop.prefetch import prefetch_context


@pytest.mark.asyncio
async def test_prefetch_context_runs_factory() -> None:
    called = False

    async def _coro():
        nonlocal called
        called = True
        return "ok"

    await prefetch_context(lambda: _coro())
    assert called


@pytest.mark.asyncio
async def test_prefetch_context_suppresses_errors() -> None:
    async def _boom():
        raise RuntimeError("failure")

    # Should not raise despite the coroutine failing.
    await prefetch_context(lambda: _boom())
