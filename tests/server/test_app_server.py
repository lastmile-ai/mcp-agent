import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from mcp_agent.server.app_server import _workflow_run
from mcp_agent.executor.workflow import WorkflowExecution


@pytest.fixture
def mock_server_context():
    """Mock server context for testing"""
    # Build a minimal ctx object compatible with new resolution helpers
    app_context = MagicMock()
    server_context = SimpleNamespace(workflows={}, context=app_context)

    ctx = MagicMock()
    ctx.request_context = SimpleNamespace(lifespan_context=server_context)
    # Ensure no attached app path is used in tests; rely on lifespan path
    ctx.fastmcp = SimpleNamespace(_mcp_agent_app=None)
    return ctx


@pytest.fixture
def mock_workflow_class():
    """Mock workflow class for testing"""

    class MockWorkflow:
        def __init__(self):
            self.name = None
            self.context = None
            self.run_async = AsyncMock()

        @classmethod
        async def create(cls, name=None, context=None):
            instance = cls()
            instance.name = name
            instance.context = context
            return instance

    # Convert create to AsyncMock that we can control
    MockWorkflow.create = AsyncMock()

    return MockWorkflow


@pytest.mark.asyncio
async def test_workflow_run_with_custom_workflow_id(
    mock_server_context, mock_workflow_class
):
    """Test that workflow_id from kwargs is passed correctly"""
    # Setup
    workflow_name = "TestWorkflow"
    mock_server_context.request_context.lifespan_context.workflows[workflow_name] = (
        mock_workflow_class
    )

    # Create mock execution result
    mock_execution = WorkflowExecution(
        workflow_id="custom-workflow-123", run_id="run-456"
    )

    # Create a mock instance
    mock_instance = mock_workflow_class()
    mock_instance.run_async.return_value = mock_execution
    mock_workflow_class.create.return_value = mock_instance

    # Call _workflow_run with custom workflow_id
    result = await _workflow_run(
        mock_server_context,
        workflow_name,
        {},  # run_parameters
        workflow_id="custom-workflow-123",
    )

    # Verify the workflow was created
    mock_workflow_class.create.assert_called_once_with(
        name=workflow_name,
        context=mock_server_context.request_context.lifespan_context.context,
    )

    # Verify run_async was called with the custom workflow_id
    mock_instance.run_async.assert_called_once()
    call_kwargs = mock_instance.run_async.call_args.kwargs
    assert "__mcp_agent_workflow_id" in call_kwargs
    assert call_kwargs["__mcp_agent_workflow_id"] == "custom-workflow-123"

    # Verify the result
    assert result["workflow_id"] == "custom-workflow-123"
    assert result["run_id"] == "run-456"


@pytest.mark.asyncio
async def test_workflow_run_with_custom_task_queue(
    mock_server_context, mock_workflow_class
):
    """Test that task_queue from kwargs is passed correctly"""
    # Setup
    workflow_name = "TestWorkflow"
    mock_server_context.request_context.lifespan_context.workflows[workflow_name] = (
        mock_workflow_class
    )

    # Create mock execution result
    mock_execution = WorkflowExecution(workflow_id="workflow-789", run_id="run-012")

    # Create a mock instance
    mock_instance = mock_workflow_class()
    mock_instance.run_async.return_value = mock_execution
    mock_workflow_class.create.return_value = mock_instance

    # Call _workflow_run with custom task_queue
    await _workflow_run(
        mock_server_context,
        workflow_name,
        {},  # run_parameters
        task_queue="custom-task-queue",
    )

    # Verify run_async was called with the custom task_queue
    mock_instance.run_async.assert_called_once()
    call_kwargs = mock_instance.run_async.call_args.kwargs
    assert "__mcp_agent_task_queue" in call_kwargs
    assert call_kwargs["__mcp_agent_task_queue"] == "custom-task-queue"


@pytest.mark.asyncio
async def test_workflow_run_with_both_custom_params(
    mock_server_context, mock_workflow_class
):
    """Test that both workflow_id and task_queue are passed correctly"""
    # Setup
    workflow_name = "TestWorkflow"
    mock_server_context.request_context.lifespan_context.workflows[workflow_name] = (
        mock_workflow_class
    )

    # Create mock execution result
    mock_execution = WorkflowExecution(
        workflow_id="custom-workflow-abc", run_id="run-xyz"
    )

    # Create a mock instance
    mock_instance = mock_workflow_class()
    mock_instance.run_async.return_value = mock_execution
    mock_workflow_class.create.return_value = mock_instance

    # Call _workflow_run with both custom parameters
    await _workflow_run(
        mock_server_context,
        workflow_name,
        {"param1": "value1"},  # run_parameters
        workflow_id="custom-workflow-abc",
        task_queue="custom-queue-xyz",
    )

    # Verify run_async was called with both custom parameters
    mock_instance.run_async.assert_called_once()
    call_kwargs = mock_instance.run_async.call_args.kwargs
    assert "__mcp_agent_workflow_id" in call_kwargs
    assert call_kwargs["__mcp_agent_workflow_id"] == "custom-workflow-abc"
    assert "__mcp_agent_task_queue" in call_kwargs
    assert call_kwargs["__mcp_agent_task_queue"] == "custom-queue-xyz"
    # Verify regular parameters are also passed
    assert "param1" in call_kwargs
    assert call_kwargs["param1"] == "value1"


@pytest.mark.asyncio
async def test_workflow_run_without_custom_params(
    mock_server_context, mock_workflow_class
):
    """Test that workflow runs normally without custom parameters"""
    # Setup
    workflow_name = "TestWorkflow"
    mock_server_context.request_context.lifespan_context.workflows[workflow_name] = (
        mock_workflow_class
    )

    # Create mock execution result
    mock_execution = WorkflowExecution(
        workflow_id="auto-generated-id", run_id="auto-run-id"
    )

    # Create a mock instance
    mock_instance = mock_workflow_class()
    mock_instance.run_async.return_value = mock_execution
    mock_workflow_class.create.return_value = mock_instance

    # Call _workflow_run without custom parameters
    await _workflow_run(
        mock_server_context,
        workflow_name,
        {"param1": "value1", "param2": 42},  # run_parameters
    )

    # Verify run_async was called without custom parameters
    mock_instance.run_async.assert_called_once()
    call_kwargs = mock_instance.run_async.call_args.kwargs
    # Verify only regular parameters are passed
    assert "__mcp_agent_workflow_id" not in call_kwargs
    assert "__mcp_agent_task_queue" not in call_kwargs
    assert "param1" in call_kwargs
    assert call_kwargs["param1"] == "value1"
    assert "param2" in call_kwargs
    assert call_kwargs["param2"] == 42


@pytest.mark.asyncio
async def test_workflow_run_preserves_user_params_with_similar_names(
    mock_server_context, mock_workflow_class
):
    """Test that user parameters with similar names are not affected"""
    # Setup
    workflow_name = "TestWorkflow"
    mock_server_context.request_context.lifespan_context.workflows[workflow_name] = (
        mock_workflow_class
    )

    # Create mock execution result
    mock_execution = WorkflowExecution(workflow_id="test-id", run_id="test-run")

    # Create a mock instance
    mock_instance = mock_workflow_class()
    mock_instance.run_async.return_value = mock_execution
    mock_workflow_class.create.return_value = mock_instance

    # Call _workflow_run with parameters that have similar names
    await _workflow_run(
        mock_server_context,
        workflow_name,
        {
            "workflow_id": "user-workflow-id",  # User's own workflow_id parameter
            "task_queue": "user-task-queue",  # User's own task_queue parameter
            "__mcp_agent_workflow_id": "should-not-happen",  # Should not be in user params
            "other_param": "value",
        },
        workflow_id="system-workflow-id",
        task_queue="system-task-queue",
    )

    # Verify run_async was called with correct separation of parameters
    mock_instance.run_async.assert_called_once()
    call_kwargs = mock_instance.run_async.call_args.kwargs

    # System parameters should use the special prefix
    assert call_kwargs["__mcp_agent_workflow_id"] == "system-workflow-id"
    assert call_kwargs["__mcp_agent_task_queue"] == "system-task-queue"

    # User parameters should be preserved as-is
    assert call_kwargs["workflow_id"] == "user-workflow-id"
    assert call_kwargs["task_queue"] == "user-task-queue"
    assert call_kwargs["other_param"] == "value"

    # The "__mcp_agent_workflow_id" from user params should not override system param
    assert call_kwargs["__mcp_agent_workflow_id"] != "should-not-happen"
