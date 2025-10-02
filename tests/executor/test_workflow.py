import asyncio
import pytest
from mcp_agent.executor.workflow import WorkflowState, WorkflowResult, Workflow
from unittest.mock import MagicMock, AsyncMock


class TestWorkflowState:
    def test_initialization(self):
        state = WorkflowState()
        assert state.status == "initialized"
        assert state.metadata == {}
        assert state.updated_at is None
        assert state.error is None

    def test_record_error(self):
        state = WorkflowState()
        try:
            raise ValueError("test error")
        except Exception as e:
            state.record_error(e)
        assert state.error is not None
        assert state.error["type"] == "ValueError"
        assert state.error["message"] == "test error"
        assert isinstance(state.error["timestamp"], float)

    def test_state_serialization(self):
        state = WorkflowState(
            status="running", metadata={"foo": "bar"}, updated_at=123.45
        )
        data = state.model_dump()
        assert data["status"] == "running"
        assert data["metadata"] == {"foo": "bar"}
        assert data["updated_at"] == 123.45


class MockWorkflow(Workflow):
    async def run(self, *args, **kwargs):
        return WorkflowResult(value="ran", metadata={"ran": True})


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.executor = MagicMock()
    context.config.execution_engine = "asyncio"
    context.workflow_registry = MagicMock()
    return context


@pytest.fixture
def workflow(mock_context):
    return MockWorkflow(name="TestWorkflow", context=mock_context)


class TestWorkflowResult:
    def test_initialization(self):
        result = WorkflowResult()
        assert result.value is None
        assert result.metadata == {}
        assert result.start_time is None
        assert result.end_time is None

    def test_with_values(self):
        result = WorkflowResult(
            value=42, metadata={"foo": "bar"}, start_time=1.0, end_time=2.0
        )
        assert result.value == 42
        assert result.metadata == {"foo": "bar"}
        assert result.start_time == 1.0
        assert result.end_time == 2.0

    def test_generic_type_handling(self):
        # Just ensure it works with different types
        result_str = WorkflowResult[str](value="test")
        result_dict = WorkflowResult[dict](value={"a": 1})
        assert result_str.value == "test"
        assert result_dict.value == {"a": 1}


class TestWorkflowBase:
    def test_initialization(self, workflow):
        assert workflow.name == "TestWorkflow"
        assert workflow.state.status == "initialized"
        assert workflow._initialized is False

    def test_id_and_run_id_properties(self, workflow):
        assert workflow.name == "TestWorkflow"
        assert workflow.id is None
        assert workflow.run_id is None

    def test_executor_property(self, workflow, mock_context):
        assert workflow.executor is mock_context.executor
        workflow.context.executor = None
        wf = MockWorkflow(name="TestWorkflow", context=workflow.context)
        with pytest.raises(ValueError):
            _ = wf.executor

    @pytest.mark.asyncio
    async def test_create_and_initialize(self, mock_context):
        wf = await MockWorkflow.create(name="WF", context=mock_context)
        assert isinstance(wf, MockWorkflow)
        assert wf._initialized is True
        assert wf.state.status in ("initializing", "initialized")

    @pytest.mark.asyncio
    async def test_initialize_and_cleanup(self, workflow):
        await workflow.initialize()
        assert workflow._initialized is True
        await workflow.cleanup()
        assert workflow._initialized is False

    @pytest.mark.asyncio
    async def test_update_state(self, workflow):
        await workflow.update_state(foo="bar", status="custom")
        assert workflow.state.foo == "bar"
        assert workflow.state.status == "custom"


class TestWorkflowAsyncMethods:
    @pytest.mark.asyncio
    async def test_run_async_asyncio(self, workflow, mock_context):
        from unittest.mock import AsyncMock

        # Setup
        workflow.context.config.execution_engine = "asyncio"
        workflow.executor.uuid.return_value = "uuid-123"
        workflow.context.workflow_registry.register = AsyncMock()

        # Make wait_for_signal never return so cancel task never completes
        async def never_return(*args, **kwargs):
            await asyncio.Future()

        workflow.executor.wait_for_signal = AsyncMock(side_effect=never_return)
        execution = await workflow.run_async()
        assert execution.run_id == "uuid-123"
        assert execution.workflow_id == "TestWorkflow"
        assert workflow._run_id == "uuid-123"
        # verify status transitions
        assert workflow.state.status == "scheduled"
        # allow the runner to pick up the task
        await asyncio.sleep(0)
        assert workflow.state.status == "running"
        # wait for completion
        await workflow._run_task
        assert workflow.state.status == "completed"

    @pytest.mark.asyncio
    async def test_parallel_workflows_unique_ids(self, mock_context):
        from unittest.mock import AsyncMock
        import uuid

        # Create multiple workflows of the same class
        workflows = []
        run_ids = []

        # Mock uuid generation to return unique values
        unique_ids = [str(uuid.uuid4()) for _ in range(3)]
        mock_context.executor.uuid.side_effect = unique_ids
        mock_context.workflow_registry.register = AsyncMock()

        # Create and start 3 workflows in parallel
        for i in range(3):
            wf = MockWorkflow(name="TestWorkflow", context=mock_context)
            wf.context.config.execution_engine = "asyncio"

            # Make wait_for_signal never return so cancel task never completes
            async def never_return(*args, **kwargs):
                await asyncio.Future()

            wf.executor.wait_for_signal = AsyncMock(side_effect=never_return)
            workflows.append(wf)

        # Start all workflows concurrently
        execution_tasks = [wf.run_async() for wf in workflows]
        executions = await asyncio.gather(*execution_tasks)
        run_ids = [exec.run_id for exec in executions]

        # Verify each workflow has a unique run_id
        assert len(set(run_ids)) == 3, "All run_ids should be unique"
        assert run_ids == unique_ids, "Run IDs should match the mocked UUIDs"

        # Verify each workflow has the same workflow_id (name)
        for wf in workflows:
            assert wf._workflow_id == "TestWorkflow"
            assert wf.id == "TestWorkflow"

        # Verify each workflow has a unique run_id
        for i, wf in enumerate(workflows):
            assert wf._run_id == unique_ids[i]
            assert wf.run_id == unique_ids[i]

        # Clean up - cancel all running tasks
        for wf in workflows:
            if hasattr(wf, "_run_task") and wf._run_task and not wf._run_task.done():
                wf._run_task.cancel()

        # Wait for all tasks to finish cancellation
        await asyncio.gather(
            *[
                wf._run_task
                for wf in workflows
                if hasattr(wf, "_run_task") and wf._run_task
            ],
            return_exceptions=True,
        )

    @pytest.mark.asyncio
    async def test_parallel_workflows_registry_tracking(self, mock_context):
        from unittest.mock import AsyncMock
        import uuid

        # Create a registry to track registrations
        registered_workflows = []

        async def mock_register(workflow, run_id, workflow_id, task):
            registered_workflows.append(
                {
                    "workflow": workflow,
                    "run_id": run_id,
                    "workflow_id": workflow_id,
                    "task": task,
                }
            )

        mock_context.workflow_registry.register = AsyncMock(side_effect=mock_register)

        # Mock uuid generation
        unique_ids = [f"run-{i}-{uuid.uuid4()!s}" for i in range(3)]
        mock_context.executor.uuid.side_effect = unique_ids

        # Create and start workflows
        workflows = []
        for i in range(3):
            wf = MockWorkflow(name="ParallelWorkflow", context=mock_context)
            wf.context.config.execution_engine = "asyncio"

            async def never_return(*args, **kwargs):
                await asyncio.Future()

            wf.executor.wait_for_signal = AsyncMock(side_effect=never_return)
            workflows.append(wf)

        # Start all workflows
        execution_tasks = [wf.run_async() for wf in workflows]
        executions = await asyncio.gather(*execution_tasks)
        run_ids = [exec.run_id for exec in executions]

        # Verify each workflow has a unique run_id
        assert len(set(run_ids)) == 3, "All run_ids should be unique"

        # Verify registry was called for each workflow
        assert len(registered_workflows) == 3

        # Verify each registration has correct data
        for i, reg in enumerate(registered_workflows):
            assert reg["workflow"] == workflows[i]
            assert reg["run_id"] == unique_ids[i]
            assert reg["workflow_id"] == "ParallelWorkflow"  # All have same workflow_id
            assert reg["task"] is not None
            assert isinstance(reg["task"], asyncio.Task)

        # Verify workflow registry can distinguish between instances
        all_run_ids = [reg["run_id"] for reg in registered_workflows]
        assert len(set(all_run_ids)) == 3, "All registered run_ids should be unique"

        # Clean up - cancel all running tasks
        for wf in workflows:
            if hasattr(wf, "_run_task") and wf._run_task and not wf._run_task.done():
                wf._run_task.cancel()

        # Wait for all tasks to finish cancellation
        await asyncio.gather(
            *[
                wf._run_task
                for wf in workflows
                if hasattr(wf, "_run_task") and wf._run_task
            ],
            return_exceptions=True,
        )

    @pytest.mark.asyncio
    async def test_cancel_no_run_id(self, workflow):
        workflow._run_id = None
        result = await workflow.cancel()
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_no_run_id(self, workflow):
        workflow._run_id = None
        result = await workflow.resume()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_status(self, workflow):
        # Should return a status dict with expected keys
        status = await workflow.get_status()
        assert isinstance(status, dict)
        assert "id" in status
        assert "name" in status
        assert "status" in status
        assert "running" in status
        assert "state" in status

    @pytest.mark.asyncio
    async def test_run_async_with_custom_workflow_id(self, mock_context):
        """Test that custom workflow_id is properly passed through"""
        workflow = MockWorkflow(name="TestWorkflow", context=mock_context)
        workflow.context.config.execution_engine = "asyncio"

        # Mock the workflow registry
        mock_context.workflow_registry.register = AsyncMock()

        # Use a custom workflow ID
        custom_workflow_id = "my-custom-workflow-id"
        execution = await workflow.run_async(__mcp_agent_workflow_id=custom_workflow_id)

        assert execution.workflow_id == custom_workflow_id
        assert workflow._workflow_id == custom_workflow_id

    @pytest.mark.asyncio
    async def test_run_async_with_temporal_custom_params(self, mock_context):
        """Test that custom workflow_id and task_queue are passed to Temporal executor"""
        workflow = MockWorkflow(name="TestWorkflow", context=mock_context)
        workflow.context.config.execution_engine = "temporal"

        # Mock the workflow registry
        mock_context.workflow_registry.register = AsyncMock()

        # Mock the Temporal executor
        mock_handle = MagicMock()
        mock_handle.id = "temporal-workflow-id"
        mock_handle.run_id = "temporal-run-id"
        mock_handle.result_run_id = None
        mock_handle.result = AsyncMock()

        workflow.executor.start_workflow = AsyncMock(return_value=mock_handle)

        # Use custom parameters
        custom_workflow_id = "my-custom-workflow-id"
        custom_task_queue = "my-custom-task-queue"

        execution = await workflow.run_async(
            __mcp_agent_workflow_id=custom_workflow_id,
            __mcp_agent_task_queue=custom_task_queue,
        )

        # Verify start_workflow was called with correct parameters
        workflow.executor.start_workflow.assert_called_once_with(
            "TestWorkflow",
            workflow_id=custom_workflow_id,
            task_queue=custom_task_queue,
            workflow_memo=None,
        )

        # Verify execution uses the handle's ID
        assert execution.workflow_id == "temporal-workflow-id"
        assert execution.run_id == "temporal-run-id"

    @pytest.mark.asyncio
    async def test_run_async_regular_params_not_affected(self, mock_context):
        """Test that regular parameters are not affected by special parameters"""

        # Create a test workflow that captures parameters
        class ParameterCaptureWorkflow(Workflow):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.params_received = None

            async def run(self, **kwargs):
                self.params_received = kwargs
                return WorkflowResult(value="test")

        workflow = ParameterCaptureWorkflow(name="TestWorkflow", context=mock_context)
        workflow.context.config.execution_engine = "asyncio"

        # Mock the workflow registry to avoid background task issues
        mock_context.workflow_registry = None

        # Use a custom workflow ID
        custom_workflow_id = "custom-id"

        # Run with both special and regular parameters
        execution = await workflow.run_async(
            __mcp_agent_workflow_id=custom_workflow_id,
            regular_param="regular_value",
            another_param=123,
        )

        # Wait for the task to complete by accessing the internal task
        if workflow._run_task:
            try:
                await workflow._run_task
            except Exception:
                pass  # Ignore any exceptions from the background task

        # Verify special parameters were not passed to run()
        assert workflow.params_received is not None
        assert "__mcp_agent_workflow_id" not in workflow.params_received
        assert "regular_param" in workflow.params_received
        assert workflow.params_received["regular_param"] == "regular_value"
        assert "another_param" in workflow.params_received
        assert workflow.params_received["another_param"] == 123

        # Verify the workflow ID was set correctly
        assert execution.workflow_id == custom_workflow_id
