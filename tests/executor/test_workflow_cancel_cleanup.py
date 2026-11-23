import asyncio
from concurrent.futures import CancelledError

import pytest

from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.config import Settings
from mcp_agent.core.context import Context
from mcp_agent.executor.executor import AsyncioExecutor
from mcp_agent.executor.workflow import Workflow
from mcp_agent.executor.workflow_registry import InMemoryWorkflowRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_finalizer", [False, True])
async def test_signal_cancellation_waits_for_run_cleanup(fail_finalizer):
    started = asyncio.Event()
    finalizing = asyncio.Event()
    release = asyncio.Event()
    order = []

    class WaitingWorkflow(Workflow):
        async def run(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finalizing.set()
                await release.wait()
                order.append("run-finally")
                if fail_finalizer:
                    raise ValueError("finalizer failure")

        async def cleanup(self):
            order.append("workflow-cleanup")

    registry = InMemoryWorkflowRegistry()
    executor = AsyncioExecutor()
    context = Context(
        config=Settings(execution_engine="asyncio"),
        executor=executor,
        workflow_registry=registry,
    )
    executor._context = context
    workflow = WaitingWorkflow(name="waiting", context=context)
    execution = await workflow.run_async()
    try:
        await asyncio.wait_for(started.wait(), 2)

        async def wait_for_listener():
            while not executor.signal_bus._pending_signals.get("cancel"):
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_listener(), 2)
        assert await registry.cancel_workflow(run_id=execution.run_id) is True
        await asyncio.wait_for(finalizing.wait(), 2)
        await asyncio.sleep(0)
        assert workflow.state.status == "cancelling"
        assert order == []
    finally:
        release.set()
        try:
            with pytest.raises(CancelledError, match="Workflow was cancelled"):
                await asyncio.wait_for(workflow._run_task, 2)
        finally:
            await LoggingConfig.shutdown()
    assert order == ["run-finally", "workflow-cleanup"]
    assert workflow.state.status == "cancelled"
