import asyncio
import random
from collections import deque

import httpx
import pytest

from mcp_agent.client.http import HTTPClientConfig, HTTPToolClient
from mcp_agent.errors.canonical import CanonicalError


def test_retry_on_server_error():
    asyncio.run(_retry_on_server_error())


async def _retry_on_server_error() -> None:
    calls = deque()

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, json={"error": "upstream"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        config = HTTPClientConfig(retry_max=3, breaker_enabled=False)
        sleeps = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        tool_client = HTTPToolClient(
            "retry-tool",
            "https://example.com",
            client=async_client,
            config=config,
            sleep=fake_sleep,
            rng=random.Random(0),
        )
        response = await tool_client.request("GET", "/resource")
        assert response.status_code == 200

    assert len(calls) == 2
    assert len(sleeps) == 1
    expected = config.retry_base_ms * random.Random(0).uniform(0.8, 1.2) / 1000.0
    assert sleeps[0] == pytest.approx(expected)


def test_retry_after_header():
    asyncio.run(_retry_after_header())


async def _retry_after_header() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        sleeps = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        tool_client = HTTPToolClient(
            "retry-after-tool",
            "https://example.com",
            client=async_client,
            config=HTTPClientConfig(retry_max=2, breaker_enabled=False),
            sleep=fake_sleep,
        )
        response = await tool_client.request("GET", "/throttle")
        assert response.status_code == 200

    assert attempts == 2
    assert sleeps == [pytest.approx(1.0)]


def test_retries_exhausted_on_timeout():
    asyncio.run(_retries_exhausted_on_timeout())


async def _retries_exhausted_on_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = HTTPToolClient(
            "timeout-tool",
            "https://example.com",
            client=async_client,
            config=HTTPClientConfig(retry_max=2, breaker_enabled=False),
        )
        with pytest.raises(CanonicalError) as exc:
            await tool_client.request("GET", "/boom")

    assert exc.value.code == "network_timeout"
