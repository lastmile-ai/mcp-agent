import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta
from temporalio.common import WorkflowIDReusePolicy
from mcp_agent.executor.temporal import TemporalExecutor, TemporalExecutorConfig


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.config.temporal = TemporalExecutorConfig(
        host="localhost:7233",
        namespace="test-namespace",
        task_queue="test-queue",
        timeout_seconds=10,
    )
    context.task_registry = MagicMock()
    context.app = MagicMock()
    context.app.workflows = MagicMock()
    return context


@pytest.fixture
def executor(mock_client, mock_context):
    config = TemporalExecutorConfig(
        host="localhost:7233",
        namespace="test-namespace",
        task_queue="test-queue",
        timeout_seconds=10,
    )
    return TemporalExecutor(config=config, client=mock_client, context=mock_context)


@pytest.mark.asyncio
async def test_ensure_client(executor):
    # Should not reconnect if client is already set
    client = await executor.ensure_client()
    assert client is executor.client


def test_wrap_as_activity(executor):
    def test_func(x=1, y=2):
        return x + y

    wrapped = executor.wrap_as_activity("test_activity", test_func)
    assert hasattr(wrapped, "__temporal_activity_definition")


@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=None)
async def test_execute_task_as_async_sync(mock_runtime, executor):
    def sync_func(x, y):
        return x + y

    result = await executor._execute_task_as_async(sync_func, 2, 3)
    assert result == 5


@pytest.mark.asyncio
async def test_execute_task_as_async_async(executor):
    async def async_func(x, y):
        return x * y

    result = await executor._execute_task_as_async(async_func, 2, 4)
    assert result == 8


@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=None)
async def test_execute_task_outside_workflow(mock_runtime, executor):
    def test_func():
        return 42

    result = await executor._execute_task(test_func)
    assert result == 42


@pytest.mark.asyncio
async def test_start_workflow(executor, mock_context):
    # Provide a mock workflow with a run method that takes a named parameter
    class DummyWorkflow:
        @staticmethod
        async def run(arg1):
            return "ok"

    mock_workflow = DummyWorkflow
    mock_context.app.workflows.get.return_value = mock_workflow
    executor.client.start_workflow = AsyncMock(return_value=AsyncMock())
    await executor.start_workflow("test_workflow", "arg1", wait_for_result=False)
    executor.client.start_workflow.assert_called_once()


@pytest.mark.asyncio
async def test_start_workflow_with_custom_workflow_id(executor, mock_context):
    """Test that custom workflow_id is used instead of auto-generated one"""

    class DummyWorkflow:
        @staticmethod
        async def run():
            return "ok"

    mock_workflow = DummyWorkflow
    mock_context.app.workflows.get.return_value = mock_workflow
    executor.client.start_workflow = AsyncMock(return_value=AsyncMock())

    custom_workflow_id = "my-custom-workflow-id"
    await executor.start_workflow(
        "test_workflow", workflow_id=custom_workflow_id, wait_for_result=False
    )

    # Verify the custom workflow_id was used
    call_args = executor.client.start_workflow.call_args
    assert call_args.kwargs["id"] == custom_workflow_id


@pytest.mark.asyncio
async def test_start_workflow_with_custom_task_queue(executor, mock_context):
    """Test that custom task_queue is used instead of config default"""

    class DummyWorkflow:
        @staticmethod
        async def run():
            return "ok"

    mock_workflow = DummyWorkflow
    mock_context.app.workflows.get.return_value = mock_workflow
    executor.client.start_workflow = AsyncMock(return_value=AsyncMock())

    custom_task_queue = "my-custom-task-queue"
    await executor.start_workflow(
        "test_workflow", task_queue=custom_task_queue, wait_for_result=False
    )

    # Verify the custom task_queue was used
    call_args = executor.client.start_workflow.call_args
    assert call_args.kwargs["task_queue"] == custom_task_queue


@pytest.mark.asyncio
async def test_start_workflow_with_both_custom_params(executor, mock_context):
    """Test that both custom workflow_id and task_queue are used"""

    class DummyWorkflow:
        @staticmethod
        async def run(param1, param2):
            return f"{param1}-{param2}"

    mock_workflow = DummyWorkflow
    mock_context.app.workflows.get.return_value = mock_workflow
    executor.client.start_workflow = AsyncMock(return_value=AsyncMock())

    custom_workflow_id = "my-custom-workflow-id"
    custom_task_queue = "my-custom-task-queue"

    await executor.start_workflow(
        "test_workflow",
        "value1",
        "value2",
        workflow_id=custom_workflow_id,
        task_queue=custom_task_queue,
        wait_for_result=False,
    )

    # Verify both custom parameters were used
    call_args = executor.client.start_workflow.call_args
    assert call_args.kwargs["id"] == custom_workflow_id
    assert call_args.kwargs["task_queue"] == custom_task_queue
    # Verify the input args were passed correctly
    assert call_args.args[1] == [
        "value1",
        "value2",
    ]  # Multi-arg workflow packs into sequence


@pytest.mark.asyncio
async def test_execute_workflow_with_custom_params(executor, mock_context):
    """Test that execute_workflow passes custom params to start_workflow"""

    class DummyWorkflow:
        @staticmethod
        async def run():
            return "result"

    mock_workflow = DummyWorkflow
    mock_context.app.workflows.get.return_value = mock_workflow

    mock_handle = AsyncMock()
    mock_handle.result.return_value = "workflow_result"
    executor.client.start_workflow = AsyncMock(return_value=mock_handle)

    custom_workflow_id = "my-custom-workflow-id"
    custom_task_queue = "my-custom-task-queue"

    result = await executor.execute_workflow(
        "test_workflow", workflow_id=custom_workflow_id, task_queue=custom_task_queue
    )

    # Verify start_workflow was called with custom params
    call_args = executor.client.start_workflow.call_args
    assert call_args.kwargs["id"] == custom_workflow_id
    assert call_args.kwargs["task_queue"] == custom_task_queue

    # Verify result was waited for
    assert result == "workflow_result"


@pytest.mark.asyncio
async def test_terminate_workflow(executor):
    mock_handle = AsyncMock()
    executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)
    await executor.terminate_workflow("workflow-id", "run-id", "Termination reason")
    executor.client.get_workflow_handle.assert_called_once_with(
        workflow_id="workflow-id", run_id="run-id"
    )
    mock_handle.terminate.assert_awaited_once_with(reason="Termination reason")


@pytest.mark.asyncio
async def test_id_reuse_policy_from_config(mock_context):
    """Test that id_reuse_policy from config is correctly mapped to temporal enum"""
    config = TemporalExecutorConfig(
        host="localhost:7233",
        namespace="test-namespace",
        task_queue="test-queue",
        id_reuse_policy="allow_duplicate_failed_only",
    )
    executor = TemporalExecutor(config=config, client=AsyncMock(), context=mock_context)

    class DummyWorkflow:
        @staticmethod
        async def run():
            return "ok"

    mock_context.app.workflows.get.return_value = DummyWorkflow
    executor.client.start_workflow = AsyncMock(return_value=AsyncMock())

    await executor.start_workflow("test_workflow", wait_for_result=False)

    call_args = executor.client.start_workflow.call_args
    assert (
        call_args.kwargs["id_reuse_policy"]
        == WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY
    )


@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=MagicMock())
@patch("temporalio.workflow.execute_activity")
async def test_timeout_seconds_prioritized_over_metadata(
    mock_execute_activity, mock_runtime, mock_context
):
    """Test that config.timeout_seconds takes priority over execution_metadata schedule_to_close_timeout"""
    config = TemporalExecutorConfig(
        host="localhost:7233",
        namespace="test-namespace",
        task_queue="test-queue",
        timeout_seconds=30,  # Config timeout
    )
    executor = TemporalExecutor(config=config, client=AsyncMock(), context=mock_context)

    # Mock a workflow task with metadata timeout
    def mock_task():
        return "result"

    mock_task.func = mock_task
    mock_task.is_workflow_task = True
    mock_task.execution_metadata = {
        "activity_name": "test_activity",
        "schedule_to_close_timeout": 60,  # Metadata timeout should be overridden
    }

    # Mock the activity registry
    mock_activity = MagicMock()
    mock_context.task_registry.get_activity.return_value = mock_activity

    mock_execute_activity.return_value = "activity_result"

    result = await executor._execute_task(mock_task)

    # Verify execute_activity was called with config timeout (30s), not metadata timeout (60s)
    mock_execute_activity.assert_called_once()
    call_args = mock_execute_activity.call_args
    assert call_args.kwargs["schedule_to_close_timeout"] == timedelta(seconds=30)
    assert result == "activity_result"


@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=MagicMock())
@patch("temporalio.workflow.execute_activity")
async def test_metadata_timeout_used_when_no_config_timeout(
    mock_execute_activity, mock_runtime, mock_context
):
    """Test that metadata timeout is used when config.timeout_seconds is None"""
    config = TemporalExecutorConfig(
        host="localhost:7233",
        namespace="test-namespace",
        task_queue="test-queue",
        # No config timeout
    )
    executor = TemporalExecutor(config=config, client=AsyncMock(), context=mock_context)

    # Mock a workflow task with metadata timeout
    def mock_task():
        return "result"

    mock_task.func = mock_task
    mock_task.is_workflow_task = True
    mock_task.execution_metadata = {
        "activity_name": "test_activity",
        "schedule_to_close_timeout": 60,  # Metadata timeout should be used
    }

    # Mock the activity registry
    mock_activity = MagicMock()
    mock_context.task_registry.get_activity.return_value = mock_activity

    mock_execute_activity.return_value = "activity_result"

    result = await executor._execute_task(mock_task)

    # Verify execute_activity was called with metadata timeout (60s)
    mock_execute_activity.assert_called_once()
    call_args = mock_execute_activity.call_args
    assert call_args.kwargs["schedule_to_close_timeout"] == timedelta(seconds=60)
    assert result == "activity_result"
