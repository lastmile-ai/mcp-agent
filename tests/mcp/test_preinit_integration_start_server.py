import pytest
import pytest_asyncio
from types import SimpleNamespace
from contextlib import asynccontextmanager

from mcp_agent.config import Settings, MCPServerSettings
from mcp_agent.mcp.mcp_server_registry import ServerRegistry

@pytest_asyncio.fixture
async def registry():
    return ServerRegistry(config=Settings())

@pytest.mark.asyncio
async def test_preinit_is_awaited_and_applied(monkeypatch, registry):
    called = {"done": False, "env": None}

    async def preinit(server_name, config, context):
        # async ensures awaitability
        env = dict(config.env or {})
        env["MARKED"] = "1"
        config.env = env
        called["done"] = True

    registry.register_pre_init_hook("github", preinit)

    captured = {}
    @asynccontextmanager
    async def fake_stdio_client(server_params):
        captured["env"] = getattr(server_params, "env", {})
        yield SimpleNamespace(), SimpleNamespace()

    # Patch stdio_client used inside start_server
    monkeypatch.setattr("mcp_agent.mcp.mcp_server_registry.stdio_client", fake_stdio_client)

    # Install a dummy server config
    registry.registry["github"] = MCPServerSettings(
        name="github",
        transport="stdio",
        env={},
        command="mcp-server-github"
    )

    async def dummy_factory(*a, **k):
        return SimpleNamespace()

    async with registry.start_server("github", client_session_factory=dummy_factory, context=None):
        pass

    assert called["done"] is True
    assert captured["env"].get("MARKED") == "1"
