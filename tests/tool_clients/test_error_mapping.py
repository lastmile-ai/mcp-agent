import asyncio

import httpx
import pytest

from mcp_agent.client.http import HTTPClientConfig, HTTPToolClient
from mcp_agent.errors.canonical import CanonicalError


@pytest.mark.parametrize(
    "status, expected_code",
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (429, "rate_limited"),
        (500, "upstream_error"),
    ],
)
def test_status_error_mapping(status: int, expected_code: str):
    asyncio.run(_status_error_mapping(status, expected_code))


async def _status_error_mapping(status: int, expected_code: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": "1"} if status == 429 else None
        return httpx.Response(status, headers=headers, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = HTTPToolClient(
            f"error-tool-{status}",
            "https://example.com",
            client=async_client,
            config=HTTPClientConfig(retry_max=0, breaker_enabled=False),
        )
        with pytest.raises(CanonicalError) as exc:
            await tool_client.request("GET", "/oops")

    assert exc.value.code == expected_code
    if status == 429:
        assert exc.value.hint == "honor Retry-After"
