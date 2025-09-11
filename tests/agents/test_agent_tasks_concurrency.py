import anyio
import pytest

from types import SimpleNamespace

from mcp.types import ListToolsResult

from mcp_agent.agents.agent import (
    AgentTasks,
    InitAggregatorRequest,
    ListToolsRequest,
)


class FakeAggregator:
    def __init__(self, server_names, connection_persistence, context, name):
        self.server_names = server_names
        self.connection_persistence = connection_persistence
        self.context = context
        self.name = name
        self.initialized = False
        self.initialized_count = 0
        self.closed = False
        self.calls = 0
        self._block = False
        self._block_event = anyio.Event()
        # Mimic MCPAggregator internal maps expected by AgentTasks.initialize_aggregator_task
        self._namespaced_tool_map = {}
        self._server_to_tool_map = {}
        self._namespaced_prompt_map = {}
        self._server_to_prompt_map = {}
        self._namespaced_resource_map = {}
        self._server_to_resource_map = {}

    def set_block(self, block: bool):
        self._block = block
        if not block:
            # release any waiters
            try:
                self._block_event.set()
            except Exception:
                pass

    async def initialize(self, force: bool = False):
        self.initialized = True
        self.initialized_count += 1

    async def list_tools(self, server_name: str | None = None) -> ListToolsResult:
        self.calls += 1
        if self._block:
            await self._block_event.wait()
        return ListToolsResult(tools=[])

    async def close(self):
        self.closed = True


@pytest.mark.anyio
async def test_lazy_reinitialize_missing_aggregator(monkeypatch):
    # Monkeypatch MCPAggregator to FakeAggregator
    from mcp_agent.agents import agent as agent_mod

    monkeypatch.setattr(agent_mod, "MCPAggregator", FakeAggregator)

    ctx = SimpleNamespace()
    tasks = AgentTasks(context=ctx)

    agent_name = "writer"
    req = InitAggregatorRequest(
        agent_name=agent_name,
        server_names=["srv1"],
        connection_persistence=True,
        force=False,
    )

    # Initialize once
    await tasks.initialize_aggregator_task(req)
    assert agent_name in tasks.server_aggregators_for_agent

    # Simulate aggregator disappearing (e.g., concurrent shutdown)
    async with tasks.server_aggregators_for_agent_lock:
        tasks.server_aggregators_for_agent.pop(agent_name, None)

    # A subsequent call should lazily re-create and initialize the aggregator
    res = await tasks.list_tools_task(
        ListToolsRequest(agent_name=agent_name, server_name=None)
    )
    assert isinstance(res, ListToolsResult)
    assert agent_name in tasks.server_aggregators_for_agent


@pytest.mark.anyio
async def test_shutdown_deferred_until_inflight_complete(monkeypatch):
    # Monkeypatch MCPAggregator to FakeAggregator
    from mcp_agent.agents import agent as agent_mod

    monkeypatch.setattr(agent_mod, "MCPAggregator", FakeAggregator)

    ctx = SimpleNamespace()
    tasks = AgentTasks(context=ctx)

    agent_name = "writer"
    req = InitAggregatorRequest(
        agent_name=agent_name,
        server_names=["srv1"],
        connection_persistence=True,
        force=False,
    )

    await tasks.initialize_aggregator_task(req)

    # Configure fake aggregator to block list_tools until we release it
    agg = tasks.server_aggregators_for_agent[agent_name]
    agg.set_block(True)

    async def call_list_tools():
        return await tasks.list_tools_task(
            ListToolsRequest(agent_name=agent_name, server_name=None)
        )

    async with anyio.create_task_group() as tg:
        # Start two concurrent calls
        tg.start_soon(
            tasks.list_tools_task,
            ListToolsRequest(agent_name=agent_name, server_name=None),
        )
        tg.start_soon(
            tasks.list_tools_task,
            ListToolsRequest(agent_name=agent_name, server_name=None),
        )

        # Allow tasks to start and increment inflight count
        await anyio.sleep(0.1)

        # Request shutdown while inflight > 0
        ok = await tasks.shutdown_aggregator_task(agent_name)
        assert ok is True

        # Aggregator should still exist due to deferred shutdown
        async with tasks.server_aggregators_for_agent_lock:
            assert agent_name in tasks.server_aggregators_for_agent

        # Release the blocked calls
        agg.set_block(False)

    # After tasks finish, aggregator should be closed and removed
    # Allow a brief moment for context manager finalizers
    await anyio.sleep(0)
    async with tasks.server_aggregators_for_agent_lock:
        assert agent_name not in tasks.server_aggregators_for_agent
