import pytest

from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager


class DummyServerRegistry:
    def __init__(self):
        self.registry = {}
        self.init_hooks = {}


@pytest.mark.anyio
async def test_connection_manager_lifecycle_single_loop():
    mgr = MCPConnectionManager(server_registry=DummyServerRegistry())
    # Enter context
    await mgr.__aenter__()
    # Disconnect (no servers) and exit
    await mgr.disconnect_all()
    await mgr.__aexit__(None, None, None)
    # Should not raise and internal task group should be cleared
    assert getattr(mgr, "_tg", None) is None
