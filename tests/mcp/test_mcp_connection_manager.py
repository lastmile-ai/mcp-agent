import pytest
import anyio
from types import SimpleNamespace

from mcp_agent.mcp.mcp_connection_manager import (
    MCPConnectionManager,
)
from mcp_agent.config import MCPServerSettings

# ---------------------------
# Test Doubles
# ---------------------------


class DummySession:
    def __init__(self, should_fail_init=False):
        self._should_fail_init = should_fail_init
        self.initialized = False
        self.closed = False
        self.server_config = None

    async def initialize(self):
        if self._should_fail_init:
            raise RuntimeError("init failed")
        self.initialized = True
        return SimpleNamespace(capabilities={"foo": "bar"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.closed = True


class DummyServerRegistry:
    def __init__(self, registry_dict):
        self.registry = registry_dict
        self.init_hooks = {}


@pytest.fixture
def server_settings():
    return MCPServerSettings(
        transport="stdio",
        command="echo",
        args=[],
    )


@pytest.fixture
def server_registry(server_settings):
    return DummyServerRegistry({"srv1": server_settings, "srv2": server_settings})


@pytest.fixture
def dummy_client_session_factory():
    def factory(*a, **k):
        return DummySession()

    return factory


@pytest.fixture
def dummy_client_session_factory_fail():
    def factory(*a, **k):
        return DummySession(should_fail_init=True)

    return factory


# ---------------------------
# Tests
# ---------------------------


@pytest.mark.anyio
async def test_launch_server_success(server_registry, dummy_client_session_factory):
    async with MCPConnectionManager(server_registry) as mgr:
        server_conn = await mgr.launch_server(
            "srv1",
            client_session_factory=dummy_client_session_factory,
        )
        await server_conn.wait_for_initialized()
        assert "srv1" in mgr.running_servers
        assert server_conn.is_healthy()
        assert server_conn.server_capabilities == {"foo": "bar"}


@pytest.mark.anyio
async def test_get_server_returns_existing_healthy(
    server_registry, dummy_client_session_factory
):
    async with MCPConnectionManager(server_registry) as mgr:
        server_conn = await mgr.launch_server(
            "srv1",
            client_session_factory=dummy_client_session_factory,
        )
        await server_conn.wait_for_initialized()
        # Should return the same object
        server2 = await mgr.get_server(
            "srv1", client_session_factory=dummy_client_session_factory
        )
        assert server2 is server_conn


@pytest.mark.anyio
async def test_get_server_recreates_unhealthy(
    server_registry, dummy_client_session_factory
):
    async with MCPConnectionManager(server_registry) as mgr:
        server_conn = await mgr.launch_server(
            "srv1",
            client_session_factory=dummy_client_session_factory,
        )
        await server_conn.wait_for_initialized()
        # Mark as unhealthy
        server_conn._error = True
        # Should create a new connection
        server2 = await mgr.get_server(
            "srv1", client_session_factory=dummy_client_session_factory
        )
        assert server2 is not server_conn
        assert server2.is_healthy()


# TODO: jerron - Figure out how to fix test
# @pytest.mark.anyio
# async def test_get_server_init_failure(
#     server_registry, dummy_client_session_factory_fail
# ):
#     # Test that initialization failure from server is properly handled
#     async with MCPConnectionManager(server_registry) as mgr:
#         # The test checks that get_server properly raises ServerInitializationError
#         # when session initialization fails
#         expected_msg = "Failed to initialize with error: 'Session initialization failed: init failed'. Check mcp_agent.config.yaml"
#         error = None

#         try:
#             await mgr.get_server(
#                 "srv1", client_session_factory=dummy_client_session_factory_fail
#             )
#         except ServerInitializationError as e:
#             error = e

#     # Verify we got the error
#     assert error is not None, "Expected ServerInitializationError was not raised"
#     # Verify it has the expected message
#     assert expected_msg in str(error), f"Unexpected error message: {str(error)}"


@pytest.mark.anyio
async def test_disconnect_server(server_registry, dummy_client_session_factory):
    async with MCPConnectionManager(server_registry) as mgr:
        server_conn = await mgr.launch_server(
            "srv1",
            client_session_factory=dummy_client_session_factory,
        )
        await server_conn.wait_for_initialized()
        await mgr.disconnect_server("srv1")
        await anyio.sleep(0)  # let event propagate
        assert server_conn._is_shutdown_requested_flag()
        assert "srv1" not in mgr.running_servers


@pytest.mark.anyio
async def test_disconnect_all(server_registry, dummy_client_session_factory):
    async with MCPConnectionManager(server_registry) as mgr:
        conn1 = await mgr.launch_server(
            "srv1", client_session_factory=dummy_client_session_factory
        )
        conn2 = await mgr.launch_server(
            "srv2", client_session_factory=dummy_client_session_factory
        )
        await conn1.wait_for_initialized()
        await conn2.wait_for_initialized()
        await mgr.disconnect_all()
        await anyio.sleep(0)
        assert conn1._is_shutdown_requested_flag()
        assert conn2._is_shutdown_requested_flag()
        assert mgr.running_servers == {}


@pytest.mark.anyio
async def test_get_server_capabilities(server_registry, dummy_client_session_factory):
    async with MCPConnectionManager(server_registry) as mgr:
        _conn = await mgr.get_server(
            "srv1", client_session_factory=dummy_client_session_factory
        )
        caps = await mgr.get_server_capabilities(
            "srv1", client_session_factory=dummy_client_session_factory
        )
        assert caps == {"foo": "bar"}
