from contextlib import asynccontextmanager
import pytest
import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mcp.types import Tool
import src.mcp_agent.mcp.mcp_aggregator as mcp_aggregator_mod


class DummyContext:
    def __init__(self):
        self.tracer = None
        self.tracing_enabled = False

        # Provide a server_registry with a start_server async context manager
        class DummySession:
            async def initialize(self):
                class InitResult:
                    capabilities = {"baz": "qux"}

                return InitResult()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class DummyServerRegistry:
            def start_server(self, server_name, client_session_factory=None):
                class DummyCtxMgr:
                    async def __aenter__(self):
                        return DummySession()

                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass

                return DummyCtxMgr()

        self.server_registry = DummyServerRegistry()
        self._mcp_connection_manager_lock = asyncio.Lock()
        self._mcp_connection_manager_ref_count = 0


@pytest.fixture
def dummy_context():
    return DummyContext()


@pytest.mark.asyncio
async def test_mcp_aggregator_init(dummy_context):
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["server1", "server2"],
        connection_persistence=False,
        context=dummy_context,
        name="test_agent",
    )
    assert aggregator.server_names == ["server1", "server2"]
    assert aggregator.connection_persistence is False
    assert aggregator.agent_name == "test_agent"
    assert not aggregator.initialized


@pytest.mark.asyncio
async def test_mcp_aggregator_initialize_sets_initialized(dummy_context):
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["server1"],
        connection_persistence=False,
        context=dummy_context,
        name="test_agent",
    )
    # Patch load_servers to avoid real async work
    with patch.object(aggregator, "load_servers", new=AsyncMock()) as mock_load_servers:
        await aggregator.initialize()
        mock_load_servers.assert_awaited_once()
        assert aggregator.initialized


@pytest.mark.asyncio
async def test_mcp_aggregator_close_no_persistence(dummy_context):
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["server1"],
        connection_persistence=False,
        context=dummy_context,
        name="test_agent",
    )
    aggregator.initialized = True
    # Should not raise, should set initialized to False
    await aggregator.close()
    assert aggregator.initialized is False


@pytest.mark.asyncio
async def test_mcp_aggregator_close_with_persistence_and_cleanup(monkeypatch):
    # Setup dummy context with connection manager attributes
    class DummyConnectionManager:
        async def disconnect_all(self):
            self.disconnected = True

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.exited = True

    context = DummyContext()
    context._mcp_connection_manager_lock = asyncio.Lock()
    context._mcp_connection_manager_ref_count = 1
    connection_manager = DummyConnectionManager()
    context._mcp_connection_manager = connection_manager

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["server1"],
        connection_persistence=True,
        context=context,
        name="test_agent",
    )
    aggregator._persistent_connection_manager = connection_manager
    aggregator.initialized = True

    # Should decrement ref count, call disconnect_all and __aexit__, and remove manager from context
    await aggregator.close()
    assert context._mcp_connection_manager_ref_count == 0
    assert not hasattr(context, "_mcp_connection_manager")
    assert aggregator.initialized is False


@pytest.mark.asyncio
async def test_mcp_aggregator_list_servers(dummy_context):
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["serverA", "serverB"],
        connection_persistence=False,
        context=dummy_context,
        name="test_agent",
    )
    # Patch load_servers to avoid real async work
    with patch.object(aggregator, "load_servers", new=AsyncMock()) as mock_load_servers:
        # Not initialized, should call load_servers and return server_names
        result = await aggregator.list_servers()
        mock_load_servers.assert_awaited_once()
        assert result == ["serverA", "serverB"]

    # If already initialized, should not call load_servers
    aggregator.initialized = True
    with patch.object(aggregator, "load_servers", new=AsyncMock()) as mock_load_servers:
        result = await aggregator.list_servers()
        mock_load_servers.assert_not_awaited()
        assert result == ["serverA", "serverB"]


@pytest.mark.asyncio
async def test_mcp_aggregator_parse_capability_name():
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1", "srv2"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    # Simulate tool maps
    tool = SimpleNamespace()
    tool.name = "toolA"
    prompt = SimpleNamespace()
    prompt.name = "promptA"
    aggregator._server_to_tool_map = {
        "srv1": [SimpleNamespace(tool=tool)],
        "srv2": [],
    }
    aggregator._server_to_prompt_map = {
        "srv1": [SimpleNamespace(prompt=prompt)],
        "srv2": [],
    }

    # Namespaced tool
    server, local = await aggregator._parse_capability_name("srv1_toolA", "tool")
    assert server == "srv1"
    assert local == "toolA"

    # Non-namespaced tool
    server, local = await aggregator._parse_capability_name("toolA", "tool")
    assert server == "srv1"
    assert local == "toolA"

    # Non-existent tool
    server, local = await aggregator._parse_capability_name("notfound", "tool")
    assert server is None
    assert local is None

    # Namespaced prompt
    server, local = await aggregator._parse_capability_name("srv1_promptA", "prompt")
    assert server == "srv1"
    assert local == "promptA"

    # Non-namespaced prompt
    server, local = await aggregator._parse_capability_name("promptA", "prompt")
    assert server == "srv1"
    assert local == "promptA"

    # Non-existent prompt
    server, local = await aggregator._parse_capability_name("notfound", "prompt")
    assert server is None
    assert local is None


@pytest.mark.asyncio
async def test_mcp_aggregator_call_tool_persistent(monkeypatch):
    # Setup aggregator with persistent connection
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1"],
        connection_persistence=True,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # Mock tool map and _parse_capability_name
    tool = SimpleNamespace()
    tool.name = "toolA"
    aggregator._namespaced_tool_map = {
        "srv1_toolA": SimpleNamespace(
            tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
        )
    }
    aggregator._server_to_tool_map = {
        "srv1": [
            SimpleNamespace(
                tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
            )
        ]
    }

    # Patch _parse_capability_name to always return ("srv1", "toolA")
    async def mock_parse(name, cap):
        return ("srv1", "toolA")

    aggregator._parse_capability_name = mock_parse

    # Mock persistent connection manager and client session
    class DummySession:
        async def call_tool(self, name, arguments=None):
            return SimpleNamespace(isError=False, content="called")

    class DummyConnManager:
        async def get_server(self, server_name, client_session_factory=None):
            return SimpleNamespace(session=DummySession())

    aggregator._persistent_connection_manager = DummyConnManager()

    # Call the tool
    result = await aggregator.call_tool("srv1_toolA", arguments={"x": 1})
    assert hasattr(result, "isError")
    assert result.isError is False
    assert result.content == "called"


class DummySession:
    async def call_tool(self, name, arguments=None):
        return SimpleNamespace(isError=False, content="called_nonpersistent")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyRegistry:
    def start_server(self, *_args, **_kw):
        return DummySession()

    @asynccontextmanager
    async def initialize_server(self, *args, **kwargs):
        yield DummySession()


@pytest.mark.asyncio
async def test_mcp_aggregator_call_tool_nonpersistent(monkeypatch):
    # Setup aggregator with non-persistent connection
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # Mock tool map and _parse_capability_name
    tool = SimpleNamespace()
    tool.name = "toolA"
    aggregator._namespaced_tool_map = {
        "srv1_toolA": SimpleNamespace(
            tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
        )
    }
    aggregator._server_to_tool_map = {
        "srv1": [
            SimpleNamespace(
                tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
            )
        ]
    }

    # Patch _parse_capability_name to always return ("srv1", "toolA")
    async def mock_parse_nonpersistent(name, cap):
        return ("srv1", "toolA")

    aggregator._parse_capability_name = mock_parse_nonpersistent

    # Patch the *server_registry* so the non-persistent path receives
    # a session with the expected `call_tool` coroutine.
    aggregator.context.server_registry = DummyRegistry()

    # Call the tool
    result = await aggregator.call_tool("srv1_toolA", arguments={"x": 2})
    assert hasattr(result, "isError")
    assert result.isError is False
    assert result.content == "called_nonpersistent"


@pytest.mark.asyncio
async def test_mcp_aggregator_call_tool_errors(monkeypatch):
    # Setup aggregator with non-persistent connection
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # --- Tool not found case ---
    # Patch _parse_capability_name to return (None, None)
    async def mock_parse_none(name, cap):
        return (None, None)

    aggregator._parse_capability_name = mock_parse_none

    result = await aggregator.call_tool("nonexistent_tool", arguments={})
    assert result.isError is True
    assert any("not found" in c.text for c in result.content)

    # --- Exception during tool call ---
    # Patch _parse_capability_name to return a valid tool
    async def mock_parse_valid(name, cap):
        return ("srv1", "toolA")

    aggregator._parse_capability_name = mock_parse_valid
    tool = SimpleNamespace()
    tool.name = "toolA"
    aggregator._namespaced_tool_map = {
        "srv1_toolA": SimpleNamespace(
            tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
        )
    }
    aggregator._server_to_tool_map = {
        "srv1": [
            SimpleNamespace(
                tool=tool, server_name="srv1", namespaced_tool_name="srv1_toolA"
            )
        ]
    }

    # Patch gen_client context manager and client session to raise exception
    class DummyClient:
        async def call_tool(self, name, arguments=None):
            raise RuntimeError("Simulated server error")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(
        mcp_aggregator_mod, "gen_client", lambda *a, **kw: DummyClient()
    )

    result = await aggregator.call_tool("srv1_toolA", arguments={})
    assert result.isError is True
    assert any("Failed to call tool" in c.text for c in result.content)


@pytest.mark.asyncio
async def test_mcp_aggregator_get_prompt(monkeypatch):
    # Setup aggregator with non-persistent connection
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # --- Successful prompt fetch ---
    prompt = SimpleNamespace()
    prompt.name = "promptA"
    aggregator._namespaced_prompt_map = {
        "srv1_promptA": SimpleNamespace(
            prompt=prompt, server_name="srv1", namespaced_prompt_name="srv1_promptA"
        )
    }
    aggregator._server_to_prompt_map = {
        "srv1": [
            SimpleNamespace(
                prompt=prompt, server_name="srv1", namespaced_prompt_name="srv1_promptA"
            )
        ]
    }

    async def mock_parse_prompt(name, cap):
        return ("srv1", "promptA")

    aggregator._parse_capability_name = mock_parse_prompt

    class DummyClient:
        async def get_prompt(self, name, arguments=None):
            # Simulate a GetPromptResult with isError=False
            result = SimpleNamespace()
            result.isError = False
            result.description = "ok"
            result.messages = ["prompt content"]
            return result

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(
        mcp_aggregator_mod, "gen_client", lambda *a, **kw: DummyClient()
    )

    result = await aggregator.get_prompt("srv1_promptA", arguments={"foo": "bar"})
    assert hasattr(result, "isError")
    assert result.isError is False
    assert result.messages == ["prompt content"]
    assert result.server_name == "srv1"
    assert result.prompt_name == "promptA"
    assert result.namespaced_name == "srv1_promptA"
    assert result.arguments == {"foo": "bar"}

    # --- Prompt not found ---
    async def mock_parse_prompt_none(name, cap):
        return (None, None)

    aggregator._parse_capability_name = mock_parse_prompt_none
    result = await aggregator.get_prompt("notfound_prompt", arguments={})
    assert result.isError is True
    assert "not found" in result.description

    # --- Exception during prompt fetch ---
    async def mock_parse_prompt_error(name, cap):
        return ("srv1", "promptA")

    aggregator._parse_capability_name = mock_parse_prompt_error

    class DummyClientError:
        async def get_prompt(self, name, arguments=None):
            raise RuntimeError("Simulated prompt error")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(
        mcp_aggregator_mod, "gen_client", lambda *a, **kw: DummyClientError()
    )

    result = await aggregator.get_prompt("srv1_promptA", arguments={})
    assert result.isError is True
    assert "Failed to get prompt" in result.description


@pytest.mark.asyncio
async def test_mcp_aggregator_list_tools_and_prompts():
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1", "srv2"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # Import real Tool and Prompt models
    from mcp.types import Tool, Prompt
    from src.mcp_agent.mcp.mcp_aggregator import NamespacedTool, NamespacedPrompt

    # Setup tool and prompt maps using real models
    tool1 = Tool(name="toolA", description="desc", inputSchema={})
    tool2 = Tool(name="toolB", description="desc", inputSchema={})
    prompt1 = Prompt(name="promptA", description="desc")
    prompt2 = Prompt(name="promptB", description="desc")

    aggregator._namespaced_tool_map = {
        "srv1_toolA": NamespacedTool(
            tool=tool1, server_name="srv1", namespaced_tool_name="srv1_toolA"
        ),
        "srv2_toolB": NamespacedTool(
            tool=tool2, server_name="srv2", namespaced_tool_name="srv2_toolB"
        ),
    }
    aggregator._server_to_tool_map = {
        "srv1": [
            NamespacedTool(
                tool=tool1, server_name="srv1", namespaced_tool_name="srv1_toolA"
            )
        ],
        "srv2": [
            NamespacedTool(
                tool=tool2, server_name="srv2", namespaced_tool_name="srv2_toolB"
            )
        ],
    }
    aggregator._namespaced_prompt_map = {
        "srv1_promptA": NamespacedPrompt(
            prompt=prompt1, server_name="srv1", namespaced_prompt_name="srv1_promptA"
        ),
        "srv2_promptB": NamespacedPrompt(
            prompt=prompt2, server_name="srv2", namespaced_prompt_name="srv2_promptB"
        ),
    }
    aggregator._server_to_prompt_map = {
        "srv1": [
            NamespacedPrompt(
                prompt=prompt1,
                server_name="srv1",
                namespaced_prompt_name="srv1_promptA",
            )
        ],
        "srv2": [
            NamespacedPrompt(
                prompt=prompt2,
                server_name="srv2",
                namespaced_prompt_name="srv2_promptB",
            )
        ],
    }

    # List all tools
    tools_result = await aggregator.list_tools()
    tool_names = sorted([t.name for t in tools_result.tools])
    assert tool_names == ["srv1_toolA", "srv2_toolB"]

    # List tools for srv1
    tools_result_srv1 = await aggregator.list_tools(server_name="srv1")
    tool_names_srv1 = [t.name for t in tools_result_srv1.tools]
    assert tool_names_srv1 == ["srv1_toolA"]

    # List all prompts
    prompts_result = await aggregator.list_prompts()
    prompt_names = sorted([p.name for p in prompts_result.prompts])
    assert prompt_names == ["srv1_promptA", "srv2_promptB"]

    # List prompts for srv2
    prompts_result_srv2 = await aggregator.list_prompts(server_name="srv2")
    prompt_names_srv2 = [p.name for p in prompts_result_srv2.prompts]
    assert prompt_names_srv2 == ["srv2_promptB"]

    # Edge case: server with no tools/prompts
    aggregator._server_to_tool_map["srv3"] = []
    aggregator._server_to_prompt_map["srv3"] = []
    tools_result_srv3 = await aggregator.list_tools(server_name="srv3")
    assert tools_result_srv3.tools == []
    prompts_result_srv3 = await aggregator.list_prompts(server_name="srv3")
    assert prompts_result_srv3.prompts == []


@pytest.mark.asyncio
async def test_mcp_aggregator_get_capabilities(monkeypatch):
    # Persistent connection case
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1"],
        connection_persistence=True,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    class DummyServerConn:
        @property
        def server_capabilities(self):
            return {"foo": "bar"}

    class DummyConnManager:
        async def get_server(self, server_name, client_session_factory=None):
            return DummyServerConn()

    aggregator._persistent_connection_manager = DummyConnManager()

    result = await aggregator.get_capabilities("srv1")
    assert result == {"foo": "bar"}

    # Persistent connection error
    class DummyConnManagerError:
        async def get_server(self, server_name, client_session_factory=None):
            raise RuntimeError("fail")

    aggregator._persistent_connection_manager = DummyConnManagerError()
    result = await aggregator.get_capabilities("srv1")
    assert result is None

    # Non-persistent connection case
    aggregator.connection_persistence = False

    class DummySession:
        async def initialize(self):
            class InitResult:
                capabilities = {"baz": "qux"}

            return InitResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(
        mcp_aggregator_mod, "gen_client", lambda *a, **kw: DummySession()
    )
    result = await aggregator.get_capabilities("srv1")
    assert result == {"baz": "qux"}

    # Non-persistent connection error
    class ErrorCtxMgr:
        async def __aenter__(self):
            raise RuntimeError("fail")

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class ErrorServerRegistry:
        def start_server(self, server_name, client_session_factory=None):
            return ErrorCtxMgr()

    # Patch only for this error case
    aggregator.context.server_registry = ErrorServerRegistry()
    with pytest.raises(RuntimeError, match="fail"):
        await aggregator.get_capabilities("srv1")


@pytest.mark.asyncio
async def test_mcp_aggregator_load_server_and_load_servers(monkeypatch):
    # Setup aggregator
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1", "srv2"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = False

    # Patch _fetch_capabilities to return different tools/prompts/resources for each server
    from mcp.types import Tool, Prompt, Resource

    tool1 = Tool(name="toolA", description="desc", inputSchema={})
    prompt1 = Prompt(name="promptA", description="desc")
    resource1 = Resource(
        uri="file://srv1/resourceA", name="resourceA", description="desc"
    )
    tool2 = Tool(name="toolB", description="desc", inputSchema={})
    prompt2 = Prompt(name="promptB", description="desc")
    resource2 = Resource(
        uri="file://srv2/resourceB", name="resourceB", description="desc"
    )

    async def fake_fetch_capabilities(server_name):
        if server_name == "srv1":
            return ("srv1", [tool1], [prompt1], [resource1])
        elif server_name == "srv2":
            return ("srv2", [tool2], [prompt2], [resource2])
        else:
            raise ValueError("Unknown server")

    monkeypatch.setattr(aggregator, "_fetch_capabilities", fake_fetch_capabilities)

    # Test load_server for srv1
    tools, prompts, resources = await aggregator.load_server("srv1")
    assert len(tools) == 1 and tools[0].name == "toolA"
    assert len(prompts) == 1 and prompts[0].name == "promptA"
    assert len(resources) == 1 and resources[0].name == "resourceA"
    assert "srv1_toolA" in aggregator._namespaced_tool_map
    assert "srv1_promptA" in aggregator._namespaced_prompt_map
    assert "srv1_resourceA" in aggregator._namespaced_resource_map

    # Test load_servers (should call for both servers)
    aggregator._namespaced_tool_map.clear()
    aggregator._server_to_tool_map.clear()
    aggregator._namespaced_prompt_map.clear()
    aggregator._server_to_prompt_map.clear()
    aggregator._namespaced_resource_map.clear()
    aggregator._server_to_resource_map.clear()
    aggregator.initialized = False
    await aggregator.load_servers()
    assert "srv1_toolA" in aggregator._namespaced_tool_map
    assert "srv2_toolB" in aggregator._namespaced_tool_map
    assert "srv1_resourceA" in aggregator._namespaced_resource_map
    assert "srv2_resourceB" in aggregator._namespaced_resource_map
    assert "srv1_promptA" in aggregator._namespaced_prompt_map
    assert "srv2_promptB" in aggregator._namespaced_prompt_map

    # Error handling: _fetch_capabilities raises for one server
    async def fetch_capabilities_with_error(server_name):
        if server_name == "srv1":
            return ("srv1", [tool1], [prompt1], [resource1])
        else:
            raise RuntimeError("Simulated error")

    monkeypatch.setattr(
        aggregator, "_fetch_capabilities", fetch_capabilities_with_error
    )
    aggregator.server_names = ["srv1", "srv2"]
    aggregator._namespaced_tool_map.clear()
    aggregator._server_to_tool_map.clear()
    aggregator._namespaced_prompt_map.clear()
    aggregator._server_to_prompt_map.clear()
    aggregator.initialized = False
    await aggregator.load_servers()
    # Should still have srv1's tools/prompts, but not srv2's
    assert "srv1_toolA" in aggregator._namespaced_tool_map
    assert "srv1_promptA" in aggregator._namespaced_prompt_map
    assert "srv2_toolB" not in aggregator._namespaced_tool_map
    assert "srv2_promptB" not in aggregator._namespaced_prompt_map


@pytest.mark.asyncio
async def test_mcp_aggregator_duplicate_tool_names():
    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["srv1", "srv2"],
        connection_persistence=False,
        context=DummyContext(),
        name="test_agent",
    )
    aggregator.initialized = True

    # Both servers have a tool named "toolX"
    tool1 = SimpleNamespace()
    tool1.name = "toolX"
    tool2 = SimpleNamespace()
    tool2.name = "toolX"

    aggregator._namespaced_tool_map = {
        "srv1_toolX": SimpleNamespace(
            tool=tool1, server_name="srv1", namespaced_tool_name="srv1_toolX"
        ),
        "srv2_toolX": SimpleNamespace(
            tool=tool2, server_name="srv2", namespaced_tool_name="srv2_toolX"
        ),
    }
    aggregator._server_to_tool_map = {
        "srv1": [
            SimpleNamespace(
                tool=tool1, server_name="srv1", namespaced_tool_name="srv1_toolX"
            )
        ],
        "srv2": [
            SimpleNamespace(
                tool=tool2, server_name="srv2", namespaced_tool_name="srv2_toolX"
            )
        ],
    }

    # Namespaced lookup
    server, local = await aggregator._parse_capability_name("srv1_toolX", "tool")
    assert server == "srv1" and local == "toolX"
    server, local = await aggregator._parse_capability_name("srv2_toolX", "tool")
    assert server == "srv2" and local == "toolX"

    # Non-namespaced lookup should resolve to the first server in the list with that tool
    server, local = await aggregator._parse_capability_name("toolX", "tool")
    assert server == "srv1" and local == "toolX"

    # If we reverse the server order, should resolve to srv2
    aggregator.server_names = ["srv2", "srv1"]
    server, local = await aggregator._parse_capability_name("toolX", "tool")
    assert server == "srv2" and local == "toolX"


@pytest.mark.asyncio
async def test_mcp_compound_server_list_tools_and_prompts(monkeypatch):
    # Patch MCPAggregator to avoid real async work
    class DummyAggregator:
        def __init__(self, server_names):
            self.server_names = server_names

        async def list_tools(self):
            class Result:
                tools = [
                    SimpleNamespace(name="srv1_toolA"),
                    SimpleNamespace(name="srv2_toolB"),
                ]

            return Result()

        async def list_prompts(self):
            class Result:
                prompts = [
                    SimpleNamespace(name="srv1_promptA"),
                    SimpleNamespace(name="srv2_promptB"),
                ]

            return Result()

    monkeypatch.setattr(mcp_aggregator_mod, "MCPAggregator", DummyAggregator)

    # Create MCPCompoundServer and test _list_tools/_list_prompts
    compound_server = mcp_aggregator_mod.MCPCompoundServer(
        server_names=["srv1", "srv2"]
    )
    tools = await compound_server._list_tools()
    tool_names = sorted([t.name for t in tools])
    assert tool_names == ["srv1_toolA", "srv2_toolB"]

    prompts = await compound_server._list_prompts()
    prompt_names = sorted([p.name for p in prompts])
    assert prompt_names == ["srv1_promptA", "srv2_promptB"]


@pytest.mark.asyncio
async def test_mcp_compound_server_call_tool_and_get_prompt(monkeypatch):
    # Patch MCPAggregator to avoid real async work
    class DummyAggregator:
        def __init__(self, server_names):
            self.server_names = server_names

        async def call_tool(self, name, arguments=None):
            if name == "fail":
                raise RuntimeError("tool error")
            return SimpleNamespace(content="tool_result")

        async def get_prompt(self, name, arguments=None):
            if name == "fail":
                raise RuntimeError("prompt error")
            return SimpleNamespace(
                isError=False, description="ok", messages=["prompt_result"]
            )

    monkeypatch.setattr(mcp_aggregator_mod, "MCPAggregator", DummyAggregator)

    compound_server = mcp_aggregator_mod.MCPCompoundServer(
        server_names=["srv1", "srv2"]
    )

    # Successful tool call
    result = await compound_server._call_tool("some_tool", arguments={"x": 1})
    assert result == "tool_result"

    # Tool call error
    result = await compound_server._call_tool("fail", arguments={})
    assert hasattr(result, "isError") and result.isError is True
    assert any("Error calling tool" in c.text for c in result.content)

    # Successful prompt fetch
    result = await compound_server._get_prompt("some_prompt", arguments={"y": 2})
    assert hasattr(result, "isError") and result.isError is False
    assert result.messages == ["prompt_result"]

    # Prompt fetch error
    result = await compound_server._get_prompt("fail", arguments={})
    assert (
        hasattr(result, "description") and "Error getting prompt" in result.description
    )


# =============================================================================
# Tool Filtering Tests
# =============================================================================


class MockServerConfig:
    """Mock server configuration for testing"""

    def __init__(self, allowed_tools=None):
        self.allowed_tools = allowed_tools


class DummyContextWithServerRegistry:
    """Extended dummy context with server registry for tool filtering tests"""

    def __init__(self, server_configs=None):
        self.tracer = None
        self.tracing_enabled = False
        self.server_configs = server_configs or {}

        class MockServerRegistry:
            def __init__(self, configs):
                self.configs = configs

            def get_server_config(self, server_name):
                return self.configs.get(server_name, MockServerConfig())

            def start_server(self, server_name, client_session_factory=None):
                class DummyCtxMgr:
                    async def __aenter__(self):
                        class DummySession:
                            async def initialize(self):
                                class InitResult:
                                    capabilities = {"tools": True}

                                return InitResult()

                        return DummySession()

                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass

                return DummyCtxMgr()

        self.server_registry = MockServerRegistry(self.server_configs)
        self._mcp_connection_manager_lock = asyncio.Lock()
        self._mcp_connection_manager_ref_count = 0


@pytest.mark.asyncio
async def test_tool_filtering_with_allowed_tools():
    """Test that tools are filtered correctly when allowed_tools is configured"""
    # Setup server config with allowed tools
    server_configs = {"test_server": MockServerConfig(allowed_tools={"tool1", "tool3"})}
    context = DummyContextWithServerRegistry(server_configs)

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["test_server"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    # Mock tools that would be returned from server
    mock_tools = [
        Tool(
            name="tool1",
            description="Description for tool1",
            inputSchema={"type": "object"},
        ),  # Should be included
        Tool(
            name="tool2",
            description="Description for tool2",
            inputSchema={"type": "object"},
        ),  # Should be filtered out
        Tool(
            name="tool3",
            description="Description for tool3",
            inputSchema={"type": "object"},
        ),  # Should be included
        Tool(
            name="tool4",
            description="Description for tool4",
            inputSchema={"type": "object"},
        ),  # Should be filtered out
    ]

    # Mock _fetch_capabilities to return our test tools
    async def mock_fetch_capabilities(server_name):
        return (None, mock_tools, [], [])  # capabilities, tools, prompts, resources

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("test_server")

    # Verify only allowed tools were added
    server_tools = aggregator._server_to_tool_map.get("test_server", [])
    assert len(server_tools) == 2

    tool_names = [tool.tool.name for tool in server_tools]
    assert "tool1" in tool_names
    assert "tool3" in tool_names
    assert "tool2" not in tool_names
    assert "tool4" not in tool_names

    # Verify namespaced tools map
    assert "test_server_tool1" in aggregator._namespaced_tool_map
    assert "test_server_tool3" in aggregator._namespaced_tool_map
    assert "test_server_tool2" not in aggregator._namespaced_tool_map
    assert "test_server_tool4" not in aggregator._namespaced_tool_map


@pytest.mark.asyncio
async def test_tool_filtering_no_filtering_when_none():
    """Test that all tools are included when allowed_tools is None"""
    # Setup server config with no filtering
    server_configs = {"test_server": MockServerConfig(allowed_tools=None)}
    context = DummyContextWithServerRegistry(server_configs)

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["test_server"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    mock_tools = [
        Tool(
            name="tool1",
            description="Description for tool1",
            inputSchema={"type": "object"},
        ),
        Tool(
            name="tool2",
            description="Description for tool2",
            inputSchema={"type": "object"},
        ),
        Tool(
            name="tool3",
            description="Description for tool3",
            inputSchema={"type": "object"},
        ),
    ]

    async def mock_fetch_capabilities(server_name):
        return (None, mock_tools, [], [])

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("test_server")

    # Verify all tools were added
    server_tools = aggregator._server_to_tool_map.get("test_server", [])
    assert len(server_tools) == 3

    tool_names = [tool.tool.name for tool in server_tools]
    assert "tool1" in tool_names
    assert "tool2" in tool_names
    assert "tool3" in tool_names


@pytest.mark.asyncio
async def test_tool_filtering_empty_allowed_tools():
    """Test behavior when allowed_tools is empty set (should filter out all tools)"""
    # Setup server config with empty allowed tools
    server_configs = {"test_server": MockServerConfig(allowed_tools=set())}
    context = DummyContextWithServerRegistry(server_configs)

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["test_server"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    mock_tools = [
        Tool(
            name="tool1",
            description="Description for tool1",
            inputSchema={"type": "object"},
        ),
        Tool(
            name="tool2",
            description="Description for tool2",
            inputSchema={"type": "object"},
        ),
    ]

    async def mock_fetch_capabilities(server_name):
        return (None, mock_tools, [], [])

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("test_server")

    # Verify no tools were added
    server_tools = aggregator._server_to_tool_map.get("test_server", [])
    assert len(server_tools) == 0

    # Verify namespaced tools map is empty for this server
    assert "test_server_tool1" not in aggregator._namespaced_tool_map
    assert "test_server_tool2" not in aggregator._namespaced_tool_map


@pytest.mark.asyncio
async def test_tool_filtering_no_server_registry():
    """Test fallback behavior when server registry is not available"""
    # Setup context without proper server registry
    context = DummyContext()  # Original dummy context without server registry

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["test_server"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    mock_tools = [
        Tool(
            name="tool1",
            description="Description for tool1",
            inputSchema={"type": "object"},
        ),
        Tool(
            name="tool2",
            description="Description for tool2",
            inputSchema={"type": "object"},
        ),
    ]

    async def mock_fetch_capabilities(server_name):
        return (None, mock_tools, [], [])

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("test_server")

    # Should include all tools when no server registry is available
    server_tools = aggregator._server_to_tool_map.get("test_server", [])
    assert len(server_tools) == 2

    tool_names = [tool.tool.name for tool in server_tools]
    assert "tool1" in tool_names
    assert "tool2" in tool_names


@pytest.mark.asyncio
async def test_tool_filtering_multiple_servers():
    """Test tool filtering works correctly with multiple servers"""
    # Setup different filtering rules for different servers
    server_configs = {
        "server1": MockServerConfig(allowed_tools={"tool1", "tool2"}),
        "server2": MockServerConfig(allowed_tools={"tool3"}),
        "server3": MockServerConfig(allowed_tools=None),  # No filtering
    }
    context = DummyContextWithServerRegistry(server_configs)

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["server1", "server2", "server3"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    # Different tools for each server
    server_tools = {
        "server1": [
            Tool(
                name="tool1",
                description="Description for tool1",
                inputSchema={"type": "object"},
            ),
            Tool(
                name="tool2",
                description="Description for tool2",
                inputSchema={"type": "object"},
            ),
            Tool(
                name="tool_extra",
                description="Description for tool_extra",
                inputSchema={"type": "object"},
            ),
        ],
        "server2": [
            Tool(
                name="tool3",
                description="Description for tool3",
                inputSchema={"type": "object"},
            ),
            Tool(
                name="tool_filtered",
                description="Description for tool_filtered",
                inputSchema={"type": "object"},
            ),
        ],
        "server3": [
            Tool(
                name="toolA",
                description="Description for toolA",
                inputSchema={"type": "object"},
            ),
            Tool(
                name="toolB",
                description="Description for toolB",
                inputSchema={"type": "object"},
            ),
        ],
    }

    async def mock_fetch_capabilities(server_name):
        tools = server_tools.get(server_name, [])
        return (None, tools, [], [])

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("server1")
        await aggregator.load_server("server2")
        await aggregator.load_server("server3")

    # Check server1 filtering
    server1_tools = aggregator._server_to_tool_map.get("server1", [])
    assert len(server1_tools) == 2
    server1_names = [tool.tool.name for tool in server1_tools]
    assert "tool1" in server1_names
    assert "tool2" in server1_names
    assert "tool_extra" not in server1_names

    # Check server2 filtering
    server2_tools = aggregator._server_to_tool_map.get("server2", [])
    assert len(server2_tools) == 1
    server2_names = [tool.tool.name for tool in server2_tools]
    assert "tool3" in server2_names
    assert "tool_filtered" not in server2_names

    # Check server3 (no filtering)
    server3_tools = aggregator._server_to_tool_map.get("server3", [])
    assert len(server3_tools) == 2
    server3_names = [tool.tool.name for tool in server3_tools]
    assert "toolA" in server3_names
    assert "toolB" in server3_names

    # Check namespaced tools map
    assert "server1_tool1" in aggregator._namespaced_tool_map
    assert "server1_tool2" in aggregator._namespaced_tool_map
    assert "server1_tool_extra" not in aggregator._namespaced_tool_map
    assert "server2_tool3" in aggregator._namespaced_tool_map
    assert "server2_tool_filtered" not in aggregator._namespaced_tool_map
    assert "server3_toolA" in aggregator._namespaced_tool_map
    assert "server3_toolB" in aggregator._namespaced_tool_map


@pytest.mark.asyncio
async def test_tool_filtering_edge_case_exact_match():
    """Test that tool filtering requires exact name matches"""
    server_configs = {
        "test_server": MockServerConfig(allowed_tools={"tool", "tool_exact"})
    }
    context = DummyContextWithServerRegistry(server_configs)

    aggregator = mcp_aggregator_mod.MCPAggregator(
        server_names=["test_server"],
        connection_persistence=False,
        context=context,
        name="test_agent",
    )

    mock_tools = [
        Tool(
            name="tool",
            description="Description for tool",
            inputSchema={"type": "object"},
        ),  # Should be included (exact match)
        Tool(
            name="tool_exact",
            description="Description for tool_exact",
            inputSchema={"type": "object"},
        ),  # Should be included (exact match)
        Tool(
            name="tool_similar",
            description="Description for tool_similar",
            inputSchema={"type": "object"},
        ),  # Should be filtered (not exact match)
        Tool(
            name="my_tool",
            description="Description for my_tool",
            inputSchema={"type": "object"},
        ),  # Should be filtered (not exact match)
    ]

    async def mock_fetch_capabilities(server_name):
        return (None, mock_tools, [], [])

    with patch.object(
        aggregator, "_fetch_capabilities", side_effect=mock_fetch_capabilities
    ):
        await aggregator.load_server("test_server")

    # Verify only exact matches were included
    server_tools = aggregator._server_to_tool_map.get("test_server", [])
    assert len(server_tools) == 2

    tool_names = [tool.tool.name for tool in server_tools]
    assert "tool" in tool_names
    assert "tool_exact" in tool_names
    assert "tool_similar" not in tool_names
    assert "my_tool" not in tool_names
