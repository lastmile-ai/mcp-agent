import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_agent.executor.workflow_registry import InMemoryWorkflowRegistry


@pytest.fixture
def registry():
    return InMemoryWorkflowRegistry()


@pytest.mark.asyncio
async def test_register_and_get_workflow_by_run_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)
    workflow = await registry.get_workflow(run_id=run_id)
    assert workflow == mock_workflow


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
async def test_resume_workflow_by_run_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.resume = AsyncMock(return_value=True)
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.resume_workflow(run_id=run_id, signal_name="resume")
    assert result is True
    mock_workflow.resume.assert_awaited_once_with("resume", None)


@pytest.mark.asyncio
async def test_resume_workflow_by_workflow_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.resume = AsyncMock(return_value=True)
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.resume_workflow(
        workflow_id=workflow_id, signal_name="resume"
    )
    assert result is True
    mock_workflow.resume.assert_awaited_once_with("resume", None)


@pytest.mark.asyncio
async def test_resume_workflow_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.resume_workflow()


@pytest.mark.asyncio
async def test_cancel_workflow_by_run_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.cancel = AsyncMock(return_value=True)
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.cancel_workflow(run_id=run_id)
    assert result is True
    mock_workflow.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_workflow_by_workflow_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.cancel = AsyncMock(return_value=True)
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.cancel_workflow(workflow_id=workflow_id)
    assert result is True
    mock_workflow.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_workflow_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.cancel_workflow()


@pytest.mark.asyncio
async def test_get_workflow_status_by_run_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.get_status = AsyncMock(
        return_value={"status": "running", "id": "workflow-id"}
    )
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.get_workflow_status(run_id=run_id)
    assert result == {"status": "running", "id": "workflow-id"}
    mock_workflow.get_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_workflow_status_by_workflow_id(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.get_status = AsyncMock(
        return_value={"status": "running", "id": "workflow-id"}
    )
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)

    result = await registry.get_workflow_status(workflow_id=workflow_id)
    assert result == {"status": "running", "id": "workflow-id"}
    mock_workflow.get_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_workflow_status_raises_error_when_no_params(registry):
    with pytest.raises(
        ValueError, match="Either run_id or workflow_id must be provided"
    ):
        await registry.get_workflow_status()


@pytest.mark.asyncio
async def test_unregister_workflow(registry):
    mock_workflow = MagicMock(name="test_workflow")
    mock_workflow.id = "workflow-id"  # Add the id attribute for unregister
    run_id = "run-id"
    workflow_id = "workflow-id"
    await registry.register(mock_workflow, run_id, workflow_id)
    await registry.unregister(run_id, workflow_id)

    assert run_id not in registry._workflows
    # After unregistering the only run for this workflow_id, the workflow_id should be removed
    assert workflow_id not in registry._workflow_ids


@pytest.mark.asyncio
async def test_list_workflow_statuses(registry):
    mock_workflow1 = MagicMock(name="wf1")
    mock_workflow1.get_status = AsyncMock(
        return_value={"id": "wf1", "status": "running"}
    )
    mock_workflow2 = MagicMock(name="wf2")
    mock_workflow2.get_status = AsyncMock(
        return_value={"id": "wf2", "status": "completed"}
    )

    await registry.register(mock_workflow1, "run1", "id1")
    await registry.register(mock_workflow2, "run2", "id2")

    statuses = await registry.list_workflow_statuses()
    assert len(statuses) == 2
    status_ids = {status["id"] for status in statuses}
    assert status_ids == {"wf1", "wf2"}


@pytest.mark.asyncio
async def test_list_workflows(registry):
    mock_workflow1 = MagicMock(name="wf1")
    mock_workflow2 = MagicMock(name="wf2")
    await registry.register(mock_workflow1, "run1", "id1")
    await registry.register(mock_workflow2, "run2", "id2")

    workflows = await registry.list_workflows()
    assert set(workflows) == {mock_workflow1, mock_workflow2}


# Tests for error cases
@pytest.mark.asyncio
async def test_workflow_id_with_nonexistent_workflow(registry):
    workflow = await registry.get_workflow(workflow_id="nonexistent")
    assert workflow is None


@pytest.mark.asyncio
async def test_resume_workflow_with_nonexistent_workflow_id(registry):
    result = await registry.resume_workflow(workflow_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_workflow_with_nonexistent_workflow_id(registry):
    result = await registry.cancel_workflow(workflow_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_workflow_status_with_nonexistent_workflow_id(registry):
    result = await registry.get_workflow_status(workflow_id="nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_resume_workflow_with_nonexistent_run_id(registry):
    result = await registry.resume_workflow(run_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_workflow_with_nonexistent_run_id(registry):
    result = await registry.cancel_workflow(run_id="nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_workflow_status_with_nonexistent_run_id(registry):
    result = await registry.get_workflow_status(run_id="nonexistent")
    assert result is None
