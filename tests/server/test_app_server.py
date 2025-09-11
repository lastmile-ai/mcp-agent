import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from mcp_agent.server.app_server import (
    _workflow_run,
    ServerContext,
    create_workflow_tools,
)
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


def test_workflow_tools_idempotent_registration():
    """Test that workflow tools are only registered once per workflow"""
    # Create mock FastMCP and context
    mock_mcp = MagicMock()
    mock_app = MagicMock()
    mock_context = MagicMock(app=mock_app)

    # Ensure the mcp mock doesn't have _registered_workflow_tools initially
    # so ServerContext.__init__ will create it
    if hasattr(mock_mcp, "_registered_workflow_tools"):
        delattr(mock_mcp, "_registered_workflow_tools")

    mock_app.workflows = {}
    # Need to mock the config and workflow_registry for ServerContext init
    mock_context.workflow_registry = None
    mock_context.config = MagicMock()
    mock_context.config.execution_engine = "asyncio"

    server_context = ServerContext(mcp=mock_mcp, context=mock_context)

    # Mock workflows
    mock_workflow_class = MagicMock()
    mock_workflow_class.__doc__ = "Test workflow"
    mock_run = MagicMock()
    mock_run.__name__ = "run"
    mock_workflow_class.run = mock_run

    mock_app.workflows = {
        "workflow1": mock_workflow_class,
        "workflow2": mock_workflow_class,
    }

    tools_created = []

    def track_tool_calls(*args, **kwargs):
        def decorator(func):
            tools_created.append(kwargs.get("name", args[0] if args else "unknown"))
            return func

        return decorator

    mock_mcp.tool = track_tool_calls

    # First call to create_workflow_tools
    create_workflow_tools(mock_mcp, server_context)

    # Verify tools were created for both workflows
    expected_tools = [
        "workflows-workflow1-run",
        "workflows-workflow2-run",
    ]

    assert len(tools_created) == 2
    for expected_tool in expected_tools:
        assert expected_tool in tools_created

    # Verify the registered workflow tools are tracked on the MCP instance
    assert hasattr(mock_mcp, "_registered_workflow_tools")
    assert mock_mcp._registered_workflow_tools == {"workflow1", "workflow2"}

    # Reset tools and call create_workflow_tools again
    tools_created.clear()
    create_workflow_tools(mock_mcp, server_context)

    # Verify no additional tools were created (idempotent)
    assert len(tools_created) == 0
    assert mock_mcp._registered_workflow_tools == {"workflow1", "workflow2"}

    # Test register_workflow with a new workflow
    new_workflow_class = MagicMock()
    new_workflow_class.__doc__ = "New workflow"
    new_mock_run = MagicMock()
    new_mock_run.__name__ = "run"
    new_workflow_class.run = new_mock_run

    server_context.register_workflow("workflow3", new_workflow_class)

    # Verify the new workflow was added and its tools created
    assert "workflow3" in server_context.workflows
    assert "workflow3" in mock_mcp._registered_workflow_tools
    assert len(tools_created) == 1  # run
    assert "workflows-workflow3-run" in tools_created

    # Test registering the same workflow again (should be idempotent)
    tools_created.clear()
    server_context.register_workflow("workflow3", new_workflow_class)

    # Should not create duplicate tools or add to workflows again
    assert len(tools_created) == 0
    assert mock_mcp._registered_workflow_tools == {
        "workflow1",
        "workflow2",
        "workflow3",
    }


def test_workflow_tools_persistent_across_sse_requests():
    """Test that workflow tools registration persists across SSE request context recreation"""
    # Create mock FastMCP instance (this persists across requests)
    mock_mcp = MagicMock()

    # Ensure the mcp mock doesn't have _registered_workflow_tools initially
    if hasattr(mock_mcp, "_registered_workflow_tools"):
        delattr(mock_mcp, "_registered_workflow_tools")

    # Mock workflows
    mock_workflow_class = MagicMock()
    mock_workflow_class.__doc__ = "Test workflow"
    mock_run = MagicMock()
    mock_run.__name__ = "run"
    mock_workflow_class.run = mock_run

    tools_created = []

    def track_tool_calls(*args, **kwargs):
        def decorator(func):
            tools_created.append(kwargs.get("name", args[0] if args else "unknown"))
            return func

        return decorator

    mock_mcp.tool = track_tool_calls

    # Simulate first SSE request - create new ServerContext
    mock_app1 = MagicMock()
    mock_context1 = MagicMock(app=mock_app1)
    mock_context1.workflow_registry = None
    mock_context1.config = MagicMock()
    mock_context1.config.execution_engine = "asyncio"
    mock_app1.workflows = {"workflow1": mock_workflow_class}
    server_context1 = ServerContext(mcp=mock_mcp, context=mock_context1)

    # Register tools in first request
    create_workflow_tools(mock_mcp, server_context1)

    # Verify tools were created
    assert len(tools_created) == 1  # run
    assert "workflows-workflow1-run" in tools_created
    assert hasattr(mock_mcp, "_registered_workflow_tools")
    assert "workflow1" in mock_mcp._registered_workflow_tools

    # Reset tools tracker
    tools_created.clear()

    # Simulate second SSE request - create NEW ServerContext (simulates fastmcp behavior)
    mock_app2 = MagicMock()
    mock_context2 = MagicMock(app=mock_app2)
    mock_context2.workflow_registry = None
    mock_context2.config = MagicMock()
    mock_context2.config.execution_engine = "asyncio"
    mock_app2.workflows = {"workflow1": mock_workflow_class}  # Same workflow
    server_context2 = ServerContext(mcp=mock_mcp, context=mock_context2)  # NEW context!

    # The MCP instance should still have the registration from the first context
    assert hasattr(mock_mcp, "_registered_workflow_tools")
    assert isinstance(
        mock_mcp._registered_workflow_tools, set
    )  # Should be a real set now

    # But the FastMCP instance should still have the persistent registration
    assert mock_mcp._registered_workflow_tools == {"workflow1"}

    # Call create_workflow_tools again - should be idempotent due to persistent storage
    create_workflow_tools(mock_mcp, server_context2)

    # Verify NO additional tools were created (idempotent)
    assert len(tools_created) == 0
    assert mock_mcp._registered_workflow_tools == {"workflow1"}
