import asyncio
import random

import httpx
import pytest

from mcp_agent.client.http import HTTPClientConfig, HTTPToolClient
from mcp_agent.errors.canonical import CanonicalError, CircuitOpenError


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_breaker_opens_and_recovers():
    asyncio.run(_breaker_opens_and_recovers())


async def _breaker_opens_and_recovers() -> None:
    failures = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal failures
        failures += 1
        if failures <= 4:
            return httpx.Response(502, json={"error": "nope"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    clock = FakeClock()
    transport = httpx.MockTransport(handler)
    config = HTTPClientConfig(
        retry_max=0,
        breaker_enabled=True,
        breaker_window=4,
        breaker_threshold=0.5,
        breaker_cooldown_ms=1000,
        half_open_max=1,
    )

    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = HTTPToolClient(
            "breaker-tool",
            "https://example.com",
            client=async_client,
            config=config,
            rng=random.Random(1),
            clock=clock,
        )

        for _ in range(4):
            with pytest.raises(CanonicalError) as exc:
                await tool_client.request("GET", "/flaky")
            assert exc.value.code == "upstream_error"

        with pytest.raises(CircuitOpenError):
            await tool_client.request("GET", "/flaky")

        clock.advance(1.5)

        response = await tool_client.request("GET", "/flaky")
        assert response.status_code == 200

        response = await tool_client.request("GET", "/flaky")
        assert response.status_code == 200
