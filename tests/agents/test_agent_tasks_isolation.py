import pytest

from mcp_agent.core.context import initialize_context
from mcp_agent.agents.agent import AgentTasks


@pytest.mark.anyio
async def test_agent_tasks_instance_scoped_state_isolation():
    ctx = await initialize_context()

    tasks_a = AgentTasks(context=ctx)
    tasks_b = AgentTasks(context=ctx)

    # They should not share aggregator dicts or locks
    assert (
        tasks_a.server_aggregators_for_agent is not tasks_b.server_aggregators_for_agent
    )
    assert (
        tasks_a.server_aggregators_for_agent_lock
        is not tasks_b.server_aggregators_for_agent_lock
    )
    assert tasks_a.agent_refcounts is not tasks_b.agent_refcounts
