import asyncio

import httpx
import pytest

from mcp_agent.adapters.github import GithubMCPAdapter
from mcp_agent.client.http import HTTPClientConfig, HTTPToolClient
from mcp_agent.errors.canonical import CanonicalError


def test_extra_fields_rejected():
    asyncio.run(_extra_fields_rejected())


async def _extra_fields_rejected() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"name": "github", "version": "1", "capabilities": {}, "extra": "nope"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = HTTPToolClient(
            "github-mcp-server",
            "https://example.com",
            client=async_client,
            config=HTTPClientConfig(breaker_enabled=False),
        )
        adapter = GithubMCPAdapter("https://example.com", client=tool_client)
        with pytest.raises(CanonicalError) as exc:
            await adapter.describe()

    assert exc.value.code == "schema_validation_error"
    assert "extra" in (exc.value.detail or "")


def test_valid_response_passes():
    asyncio.run(_valid_response_passes())


async def _valid_response_passes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"name": "github", "version": "1", "capabilities": {"fs": {}}},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = HTTPToolClient(
            "github-mcp-server",
            "https://example.com",
            client=async_client,
            config=HTTPClientConfig(breaker_enabled=False),
        )
        adapter = GithubMCPAdapter("https://example.com", client=tool_client)
        response = await adapter.describe()

    assert response.name == "github"
    assert response.version == "1"
