from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

from mcp_agent.config import MCPServerSettings, MCPSettings, Settings
from mcp_agent.mcp.mcp_server_registry import ServerRegistry


class DummySession:
    def __init__(self, read_stream, write_stream, read_timeout_seconds, **kwargs):
        self.read_timeout_seconds = read_timeout_seconds

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


@asynccontextmanager
async def dummy_stdio_client(server_name: str, server):
    yield (None, None)


def make_registry(**server_kwargs) -> ServerRegistry:
    config = Settings(
        mcp=MCPSettings(
            servers={
                "test_server": MCPServerSettings(
                    transport="stdio",
                    command="echo",
                    args=["hello"],
                    **server_kwargs,
                )
            }
        )
    )
    return ServerRegistry(config=config)


@pytest.mark.asyncio
async def test_start_server_read_timeout_is_in_seconds(monkeypatch):
    """read_timeout_seconds must be interpreted as seconds, not days."""
    monkeypatch.setattr(
        "mcp_agent.mcp.mcp_server_registry.filtered_stdio_client",
        dummy_stdio_client,
    )

    registry = make_registry(read_timeout_seconds=30)

    async with registry.start_server(
        "test_server", client_session_factory=DummySession
    ) as session:
        assert session.read_timeout_seconds == timedelta(seconds=30)


@pytest.mark.asyncio
async def test_start_server_read_timeout_absent(monkeypatch):
    monkeypatch.setattr(
        "mcp_agent.mcp.mcp_server_registry.filtered_stdio_client",
        dummy_stdio_client,
    )

    registry = make_registry()

    async with registry.start_server(
        "test_server", client_session_factory=DummySession
    ) as session:
        assert session.read_timeout_seconds is None
