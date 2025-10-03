from __future__ import annotations

import asyncio
import pytest

from mcp_agent.app import MCPApp
from mcp_agent.core.context import initialize_context
from mcp_agent.agents.agent import Agent
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.tracing.token_counter import TokenCounter
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams


@pytest.mark.asyncio
async def test_app_convenience_metrics_and_watch():
    app = MCPApp(name="test_app")

    usage_updates = []

    async def on_app_usage(node, usage):
        usage_updates.append(usage.total_tokens)

    async with app.run():
        # Ensure root node exists and query convenience methods
        root_node = await app.get_token_node()
        assert root_node is not None

        # Watch root
        watch_id = await app.watch_tokens(on_app_usage, throttle_ms=0)
        assert watch_id is not None

        # Record usage at current scope (app is on the stack)
        ctx = app.context
        await ctx.token_counter.record_usage(input_tokens=20, output_tokens=10)

        # Allow async callbacks to run
        await asyncio.sleep(0.05)

        # Verify convenience methods reflect usage
        usage = await app.get_token_usage()
        assert usage is not None
        assert usage.total_tokens == 30

        summary = await app.get_token_summary()
        assert summary.usage.total_tokens == 30

    # Watch callback fired at least once
    assert any(v >= 30 for v in usage_updates)


class _DummyWorkflow(Workflow[str]):
    async def run(self, *args, **kwargs) -> WorkflowResult[str]:
        return WorkflowResult(value="ok")


class _DummyLLM(AugmentedLLM[str, str]):
    provider = "TestProvider"

    async def generate(self, message, request_params: RequestParams | None = None):
        return ["ok"]

    async def generate_str(
        self, message, request_params: RequestParams | None = None
    ) -> str:
        return "ok"

    async def generate_structured(
        self, message, response_model, request_params: RequestParams | None = None
    ):
        return response_model()


@pytest.mark.asyncio
async def test_agent_convenience_and_disambiguation():
    ctx = await initialize_context()
    counter: TokenCounter = ctx.token_counter

    # Two agents with same name
    a1 = Agent(name="dup_agent", context=ctx)
    a2 = Agent(name="dup_agent", context=ctx)

    # Push usage for each separately in this task
    await counter.push(a1.name, "agent", {"agent_id": "A1"})
    await counter.record_usage(50, 20, model_name="m", provider="p")
    await counter.pop()

    await counter.push(a2.name, "agent", {"agent_id": "A2"})
    await counter.record_usage(30, 10, model_name="m", provider="p")
    await counter.pop()

    # Single get_token_usage is ambiguous; return_all_matches should list both nodes
    nodes = await a1.get_token_node(return_all_matches=True)
    assert isinstance(nodes, list) and len(nodes) == 2

    # Watch by name should trigger for both nodes if they receive updates
    callbacks = []

    async def on_agent_usage(node, usage):
        callbacks.append((node.metadata.get("agent_id"), usage.total_tokens))

    watch_id = await a1.watch_tokens(on_agent_usage, throttle_ms=0)
    assert watch_id is not None

    # Update both nodes again
    # We need to re-push each node to be current, then record
    # Note: we can bind the current task to the node by pushing the same name/type under the app root
    await counter.push(a1.name, "agent", {"agent_id": "A1"})
    await counter.record_usage(5, 5, model_name="m", provider="p")
    await counter.pop()

    await counter.push(a2.name, "agent", {"agent_id": "A2"})
    await counter.record_usage(5, 5, model_name="m", provider="p")
    await counter.pop()

    await asyncio.sleep(0.05)
    assert len(callbacks) >= 2
    ids = [cid for (cid, _u) in callbacks if cid in ("A1", "A2")]
    # We may get multiple callbacks per node; ensure both node IDs appeared
    assert "A1" in ids and "A2" in ids


@pytest.mark.asyncio
async def test_workflow_convenience_with_ids():
    ctx = await initialize_context()
    counter: TokenCounter = ctx.token_counter

    wf = _DummyWorkflow(name="wfX", context=ctx)
    # Simulate workflow IDs (normally set in run_async)
    wf._workflow_id = "WID_1"
    wf._run_id = "RUN_2"

    # Create two workflow nodes with same name, different IDs
    await counter.push("wfX", "workflow", {"workflow_id": "WID_1", "run_id": "RUN_1"})
    await counter.record_usage(10, 5, model_name="m", provider="p")
    await counter.pop()

    await counter.push("wfX", "workflow", {"workflow_id": "WID_1", "run_id": "RUN_2"})
    await counter.record_usage(7, 3, model_name="m", provider="p")
    await counter.pop()

    # By run_id, should resolve to the RUN_2 node
    node = await wf.get_token_node()
    assert node is not None
    assert node.metadata.get("run_id") == "RUN_2"

    usage = await wf.get_token_usage()
    assert usage is not None
    # By default, workflow convenience resolves to this instance's run_id (RUN_2)
    assert usage.total_tokens == 7 + 3


@pytest.mark.asyncio
async def test_llm_convenience_and_watch():
    ctx = await initialize_context()
    llm = _DummyLLM(context=ctx, name="llmA")

    # Manually create LLM node and record usage
    await ctx.token_counter.push(llm.name, "llm")
    await ctx.token_counter.record_usage(12, 8, model_name="m", provider="p")
    await ctx.token_counter.pop()

    usage = await llm.get_token_usage()
    assert usage is not None and usage.total_tokens == 20

    got = []

    async def on_llm(node, u):
        got.append(u.total_tokens)

    wid = await llm.watch_tokens(on_llm, throttle_ms=0)
    assert wid is not None

    # Update llm again
    await ctx.token_counter.push(llm.name, "llm")
    await ctx.token_counter.record_usage(3, 2, model_name="m", provider="p")
    await ctx.token_counter.pop()

    await asyncio.sleep(0.05)
    assert any(v >= 25 for v in got)
