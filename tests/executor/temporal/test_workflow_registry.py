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
    mock_workflow.name = "test_workflow"
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
    mock_workflow.name = "test_workflow"
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


# Tests for new workflow_id functionality
@pytest.mark.asyncio
async def test_get_workflow_by_workflow_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    # Test getting workflow by workflow_id only
    workflow = await registry.get_workflow(workflow_id=workflow_id)
    assert workflow == mock_workflow


@pytest.mark.asyncio
async def test_get_workflow_by_workflow_id_latest_run(registry):
    mock_workflow1 = MagicMock(name="test_workflow1")
    mock_workflow2 = MagicMock(name="test_workflow2")
    workflow_id = "workflow-id"

    # Register two runs for the same workflow
    await registry.register(mock_workflow1, "run-id-1", workflow_id)
    await registry.register(mock_workflow2, "run-id-2", workflow_id)

    # Should return the latest run (run-id-2)
    workflow = await registry.get_workflow(workflow_id=workflow_id)
    assert workflow == mock_workflow2


@pytest.mark.asyncio
async def test_get_workflow_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.get_workflow()


@pytest.mark.asyncio
async def test_resume_workflow_by_workflow_id(registry, mock_executor):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    mock_workflow.name = "test_workflow"
    await registry.register(mock_workflow, run_id, workflow_id)

    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)

    result = await registry.resume_workflow(
        workflow_id=workflow_id, signal_name="resume", payload={"data": "value"}
    )

    assert result is True
    mock_handle.signal.assert_awaited_once_with("resume", {"data": "value"})
    mock_executor.client.get_workflow_handle.assert_called_with(
        workflow_id=workflow_id, run_id=run_id
    )


@pytest.mark.asyncio
async def test_resume_workflow_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.resume_workflow()


@pytest.mark.asyncio
async def test_cancel_workflow_by_workflow_id(registry, mock_executor):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    mock_workflow.name = "test_workflow"
    await registry.register(mock_workflow, run_id, workflow_id)

    mock_handle = MagicMock()
    mock_handle.cancel = AsyncMock()
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)

    result = await registry.cancel_workflow(workflow_id=workflow_id)

    assert result is True
    mock_handle.cancel.assert_awaited_once()
    mock_executor.client.get_workflow_handle.assert_called_with(
        workflow_id=workflow_id, run_id=run_id
    )


@pytest.mark.asyncio
async def test_cancel_workflow_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.cancel_workflow()


@pytest.mark.asyncio
async def test_get_workflow_status_by_workflow_id(registry, mock_executor):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.id = "workflow-id"
    mock_workflow.name = "test_workflow"
    run_id = "run-id"
    workflow_id = "workflow-id"

    # Mock workflow.get_status()
    mock_workflow.get_status = AsyncMock(
        return_value={"status": "running", "id": workflow_id}
    )

    await registry.register(mock_workflow, run_id, workflow_id)

    # Mock the _get_temporal_workflow_status method
    registry._get_temporal_workflow_status = AsyncMock(
        return_value={"temporal_status": "active"}
    )

    result = await registry.get_workflow_status(workflow_id=workflow_id)

    assert result is not False
    assert result["status"] == "running"
    assert result["temporal"]["temporal_status"] == "active"


@pytest.mark.asyncio
async def test_get_workflow_status_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.get_workflow_status()


@pytest.mark.asyncio
async def test_workflow_id_with_nonexistent_workflow(registry):
    # Test that requesting a nonexistent workflow_id returns None
    workflow = await registry.get_workflow(workflow_id="nonexistent")
    assert workflow is None


@pytest.mark.asyncio
async def test_resume_workflow_with_nonexistent_workflow_id(registry, mock_executor):
    # Test that resuming a nonexistent workflow_id returns False
    result = await registry.resume_workflow(workflow_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_workflow_with_nonexistent_workflow_id(registry, mock_executor):
    # Test that canceling a nonexistent workflow_id returns False
    result = await registry.cancel_workflow(workflow_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_workflow_status_with_nonexistent_workflow_id(
    registry, mock_executor
):
    # Test that getting status of nonexistent workflow_id returns False
    result = await registry.get_workflow_status(workflow_id="nonexistent")
    assert result is False
