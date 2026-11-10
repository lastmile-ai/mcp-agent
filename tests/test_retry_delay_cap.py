import pytest

from mcp_agent.cli.utils import retry


@pytest.mark.parametrize(
    ("initial", "expected"), [(10.0, [2.0, 2.0]), (0.5, [0.5, 1.0])]
)
def test_sync_retry_delay_cap(
    monkeypatch: pytest.MonkeyPatch, initial: float, expected: list[float]
) -> None:
    delays = []
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary")
        return "done"

    monkeypatch.setattr(retry.time, "sleep", delays.append)
    assert (
        retry.retry_with_exponential_backoff(
            operation, initial_delay=initial, max_delay=2.0
        )
        == "done"
    )
    assert delays == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial", "expected"), [(10.0, [2.0, 2.0]), (0.5, [0.5, 1.0])]
)
async def test_async_retry_delay_cap(
    monkeypatch: pytest.MonkeyPatch, initial: float, expected: list[float]
) -> None:
    delays = []
    calls = 0

    async def sleep(delay):
        delays.append(delay)

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary")
        return "done"

    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    assert (
        await retry.retry_async_with_exponential_backoff(
            operation, initial_delay=initial, max_delay=2.0
        )
        == "done"
    )
    assert delays == expected
