import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_agent.executor.temporal.workflow_registry import TemporalWorkflowRegistry


@pytest.fixture
def mock_executor():
    executor = AsyncMock()
    executor.client = AsyncMock()
    return executor


@pytest.fixture
def registry(mock_executor):
    return TemporalWorkflowRegistry(executor=mock_executor)


@pytest.mark.asyncio
async def test_register_and_get_workflow(registry):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)
    workflow = await registry.get_workflow(run_id=run_id)
    assert workflow == mock_workflow
    assert registry._workflow_ids[workflow_id] == [run_id]


@pytest.mark.asyncio
async def test_unregister_workflow(registry):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)
    await registry.unregister(run_id, workflow_id)
    assert run_id not in registry._local_workflows
    assert workflow_id not in registry._workflow_ids


@pytest.mark.asyncio
async def test_resume_workflow(registry, mock_executor):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    mock_workflow.name = workflow_id  # Ensure workflow.name matches workflow_id
    await registry.register(mock_workflow, run_id, workflow_id)

    # Use MagicMock with async signal method
    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)
    result = await registry.resume_workflow(
        run_id=run_id, signal_name="resume", payload={"data": "value"}
    )
    assert result is True
    mock_handle.signal.assert_awaited_once_with("resume", {"data": "value"})


@pytest.mark.asyncio
async def test_resume_workflow_signal_error(registry, mock_executor, caplog):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    mock_workflow.name = workflow_id
    await registry.register(mock_workflow, run_id, workflow_id)

    # Mock handle whose signal method raises an exception
    class SignalError(Exception):
        pass

    mock_handle = MagicMock()

    async def raise_signal_error(*args, **kwargs):
        raise SignalError("signal failed")

    mock_handle.signal = AsyncMock(side_effect=raise_signal_error)
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)

    with caplog.at_level("ERROR"):
        result = await registry.resume_workflow(
            run_id=run_id, signal_name="resume", payload={"data": "value"}
        )
    assert result is False


@pytest.mark.asyncio
async def test_cancel_workflow(registry, mock_executor):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)
    mock_handle = MagicMock()
    mock_handle.cancel = AsyncMock()
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)
    result = await registry.cancel_workflow(run_id=run_id)
    assert result is True
    mock_handle.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_workflow_status_error(registry, mock_executor):
    # Should return error status if workflow_id is missing
    result = await registry.get_workflow_status("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_list_workflows(registry):
    mock_workflow1 = MagicMock(name="wf1")
    mock_workflow2 = MagicMock(name="wf2")
    await registry.register(mock_workflow1, "run1", "id1")
    await registry.register(mock_workflow2, "run2", "id2")
    workflows = await registry.list_workflows()
    assert set(workflows) == {mock_workflow1, mock_workflow2}
