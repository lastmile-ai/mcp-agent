import asyncio
from unittest.mock import Mock

import pytest

from mcp_agent.agents import agent as agent_module
from mcp_agent.agents.agent import Agent, AgentTasks, InitAggregatorResponse
from mcp_agent.core.context import Context
from mcp_agent.executor import executor
from mcp_agent.tracing.telemetry import telemetry


@pytest.fixture
def local_agent(monkeypatch):
    monkeypatch.setattr(agent_module, "logger", Mock())
    monkeypatch.setattr(executor, "logger", Mock())
    context = Context(executor=executor.AsyncioExecutor(), tracing_enabled=False)
    agent = Agent(name="local-agent", server_names=[], context=context)
    return context, agent


async def bounded(awaitable):
    return await asyncio.wait_for(awaitable, 5)


async def outcome(awaitable):
    try:
        await bounded(awaitable)
    except Exception as exc:
        return exc
    return None


async def initial_ok(self, request):
    return InitAggregatorResponse(initialized=True)


@pytest.mark.asyncio
async def test_initialize_surfaces_original_activity_error_and_can_retry(
    local_agent, monkeypatch
):
    context, agent = local_agent
    failure = RuntimeError("local discovery failed")
    calls = []

    async def initialize(self, request):
        calls.append(request.agent_name)
        if len(calls) == 1:
            raise failure
        return InitAggregatorResponse(initialized=True)

    monkeypatch.setattr(AgentTasks, "initialize_aggregator_task", initialize)
    with telemetry.use_context(context):
        error = await outcome(agent.initialize())
        state_after_failure = agent.initialized
        await bounded(agent.initialize())
    print(
        f"initialize: caught={error!r}, state_after_failure={state_after_failure}, calls={calls}"
    )
    assert error is failure
    assert not state_after_failure and agent.initialized
    assert calls == ["local-agent", "local-agent"]


@pytest.mark.asyncio
async def test_shutdown_surfaces_original_activity_error_and_can_retry(
    local_agent, monkeypatch
):
    context, agent = local_agent
    failure = RuntimeError("local teardown failed before cleanup")
    calls = []

    async def shutdown(self, name):
        calls.append(name)
        if len(calls) == 1:
            raise failure
        return True

    monkeypatch.setattr(AgentTasks, "initialize_aggregator_task", initial_ok)
    monkeypatch.setattr(AgentTasks, "shutdown_aggregator_task", shutdown)
    with telemetry.use_context(context):
        await bounded(agent.initialize())
        assert agent.initialized
        error = await outcome(agent.shutdown())
        state_after_failure = agent.initialized
        await bounded(agent.shutdown())
    print(
        f"shutdown: caught={error!r}, state_after_failure={state_after_failure}, calls={calls}"
    )
    assert error is failure
    assert state_after_failure and not agent.initialized
    assert calls == ["local-agent", "local-agent"]


@pytest.mark.asyncio
async def test_false_activity_results_keep_existing_lifecycle_behavior(
    local_agent, monkeypatch
):
    context, agent = local_agent
    init_calls = []
    close_calls = []

    async def initialize(self, request):
        init_calls.append(request.agent_name)
        return InitAggregatorResponse(initialized=len(init_calls) == 2)

    async def shutdown(self, name):
        close_calls.append(name)
        return len(close_calls) == 2

    monkeypatch.setattr(AgentTasks, "initialize_aggregator_task", initialize)
    monkeypatch.setattr(AgentTasks, "shutdown_aggregator_task", shutdown)
    with telemetry.use_context(context):
        with pytest.raises(RuntimeError) as init_error:
            await bounded(agent.initialize())
        assert str(init_error.value).startswith(
            "Failed to initialize agent local-agent."
        )
        assert not agent.initialized
        await bounded(agent.initialize())
        assert agent.initialized
        with pytest.raises(RuntimeError) as close_error:
            await bounded(agent.shutdown())
        assert str(close_error.value).startswith(
            "Failed to shutdown agent local-agent."
        )
        assert agent.initialized
        await bounded(agent.shutdown())
        assert not agent.initialized
        await bounded(agent.shutdown())
    assert init_calls == close_calls == ["local-agent", "local-agent"]


@pytest.mark.asyncio
async def test_executor_still_returns_activity_failure_as_a_value(local_agent):
    context, _ = local_agent
    failure = RuntimeError("executor returns this object")

    async def run():
        raise failure

    with telemetry.use_context(context):
        assert await bounded(context.executor.execute(run)) is failure
