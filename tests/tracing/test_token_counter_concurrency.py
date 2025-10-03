import asyncio
from typing import List

import pytest

from mcp_agent.tracing.token_counter import TokenCounter


@pytest.mark.asyncio
async def test_concurrent_workflows_and_agents_isolated_stacks():
    counter = TokenCounter()

    # Create global app root (as MCPApp.run() would do)
    await counter.push("app", "app", {"env": "test"})

    # Worker that simulates a workflow with a nested agent and an LLM call
    async def worker(i: int, paths: List[List[str]]):
        workflow_name = f"workflow_{i}"
        agent_name = f"agent_{i}"

        # Push workflow and agent scopes
        await counter.push(workflow_name, "workflow")
        await counter.push(agent_name, "agent")

        # Capture current path inside the nested scopes (for isolation check)
        paths.append(await counter.get_current_path())

        # Simulate an LLM call within the agent and record tokens
        await counter.push(f"llm_call_{i}", "llm", {"provider": "TestProvider"})
        await counter.record_usage(
            input_tokens=100,
            output_tokens=50,
            model_name="test-model",
            provider="TestProvider",
        )
        await counter.pop()  # llm

        # Pop agent and workflow
        await counter.pop()  # agent
        await counter.pop()  # workflow

    paths: List[List[str]] = []

    # Run many workers concurrently
    await asyncio.gather(*(worker(i, paths) for i in range(10)))

    # Validate that paths captured were isolated per task
    assert all(p[:1] == ["app"] for p in paths)
    assert len(paths) == 10
    # Ensure each path had exactly 3 levels: app -> workflow_i -> agent_i
    assert all(len(p) == 3 for p in paths)

    # Validate the resulting tree structure
    tree = await counter.get_tree()
    assert tree is not None
    assert tree["name"] == "app"
    # Expect 10 workflows directly under app
    workflow_children = [c for c in tree["children"] if c["type"] == "workflow"]
    assert len(workflow_children) == 10
    # Each workflow should have one agent child, and each agent one llm child
    for wf in workflow_children:
        assert len(wf["children"]) == 1
        agent = wf["children"][0]
        assert agent["type"] == "agent"
        assert len(agent["children"]) == 1
        llm = agent["children"][0]
        assert llm["type"] == "llm"
        # Each agent subtree total should be 150
        assert agent["aggregate_usage"]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_concurrent_record_usage_with_scope_context_manager():
    counter = TokenCounter()
    await counter.push("app", "app")

    async def worker(i: int):
        async with counter.scope(f"workflow_{i}", "workflow"):
            async with counter.scope(f"agent_{i}", "agent"):
                async with counter.scope(f"llm_call_{i}", "llm", {"provider": "Test"}):
                    await counter.record_usage(120, 30, model_name="m", provider="Test")

    await asyncio.gather(*(worker(i) for i in range(5)))

    # Validate tree usage
    tree = await counter.get_tree()
    assert tree is not None
    # Expect 5 workflow children each with 1 agent and 1 llm
    workflows = [c for c in tree["children"] if c["type"] == "workflow"]
    assert len(workflows) == 5
    for wf in workflows:
        agent = wf["children"][0]
        llm = agent["children"][0]
        assert llm["aggregate_usage"]["total_tokens"] == 150
        assert agent["aggregate_usage"]["total_tokens"] == 150
        assert wf["aggregate_usage"]["total_tokens"] == 150
