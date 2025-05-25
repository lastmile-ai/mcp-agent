import pytest
from mcp_agent.executor.workflow import WorkflowState, WorkflowResult, Workflow
from unittest.mock import MagicMock


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
        assert workflow.id == "TestWorkflow"
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
        workflow.executor.wait_for_signal = AsyncMock(return_value=None)
        run_id = await workflow.run_async()
        assert run_id == "uuid-123"
        assert workflow._run_id == "uuid-123"
        assert workflow.state.status in ("scheduled", "running", "completed")

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
