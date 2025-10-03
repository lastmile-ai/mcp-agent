import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from mcp_agent.app import MCPApp
from mcp_agent.core.context import Context
from mcp_agent.config import Settings
from mcp_agent.human_input.types import HumanInputResponse


class TestMCPApp:
    """Test cases for the MCPApp class."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Context with necessary attributes."""
        mock_context = MagicMock(spec=Context)
        mock_context.config = MagicMock(spec=Settings)
        mock_context.config.name = None
        mock_context.config.description = None
        mock_context.server_registry = MagicMock()
        mock_context.task_registry = MagicMock()
        mock_context.decorator_registry = MagicMock()
        mock_context.executor = MagicMock()
        mock_context.executor.execution_engine = MagicMock()
        mock_context.session_id = "test-session-id"
        mock_context.tracer = (
            MagicMock()
        )  # Add tracer attribute for tests that require it
        mock_context.tracing_enabled = False
        mock_context.upstream_session = None
        mock_context.tracing_config = None
        mock_context.token_counter = None  # Add token_counter attribute
        return mock_context

    @pytest.fixture
    def basic_app(self):
        """Create a basic MCPApp for testing."""
        return MCPApp(name="test_app")

    @pytest.fixture
    def human_input_callback(self):
        """Create a human input callback function."""

        async def callback(request):
            return HumanInputResponse(
                request_id=request.request_id, response="Test human input response"
            )

        return AsyncMock(side_effect=callback)

    @pytest.fixture
    def signal_notification(self):
        """Create a signal notification callback."""

        async def callback(signal_type, **kwargs):
            return "Signal received"

        return AsyncMock(side_effect=callback)

    @pytest.fixture
    def test_workflow(self):
        """Create a test workflow class."""

        class TestWorkflow:
            def __init__(self):
                self.executed = False

            async def run(self):
                self.executed = True
                return "Workflow executed"

        return TestWorkflow

    @pytest.fixture
    def test_task(self, request):
        """Create a test task function with a unique name per test to avoid collisions."""

        async def task_function(param1: str, param2: int = 0):
            """A test task function.

            Args:
                param1: String parameter
                param2: Integer parameter with default

            Returns:
                Task result
            """
            return f"Task executed with {param1} and {param2}"

        # Ensure a unique function identity to avoid activity name collisions across tests
        task_function.__name__ = f"task_function_{request.node.name}"
        task_function.__qualname__ = f"task_function_{request.node.name}"

        return task_function

    #
    # Initialization Tests
    #

    @pytest.mark.asyncio
    async def test_initialization_minimal(self):
        """Test MCPApp initialization with minimal parameters."""
        app = MCPApp(name="test_app")

        assert app.name == "test_app"
        assert app._human_input_callback is None
        assert app._signal_notification is None
        assert app._upstream_session is None
        assert app._model_selector is None
        assert app._workflows == {}
        assert app._logger is None
        assert app._context is None
        assert app._initialized is False

    @pytest.mark.asyncio
    async def test_initialization_with_custom_settings(self):
        """Test initialization with custom settings."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.name = None
        mock_settings.description = None
        app = MCPApp(name="test_app", settings=mock_settings)

        assert app._config is mock_settings

    @pytest.mark.asyncio
    async def test_initialization_with_settings_path(self):
        """Test initialization with settings path."""
        app = MCPApp(name="test_app", settings="path/to/settings.yaml")

        assert app._config is not None

    @pytest.mark.asyncio
    async def test_initialization_with_callbacks(
        self, human_input_callback, signal_notification
    ):
        """Test initialization with callbacks."""
        app = MCPApp(
            name="test_app",
            human_input_callback=human_input_callback,
            signal_notification=signal_notification,
        )

        assert app._human_input_callback is human_input_callback
        assert app._signal_notification is signal_notification

    @pytest.mark.asyncio
    async def test_initialization_with_upstream_session(self):
        """Test initialization with upstream session."""
        mock_session = MagicMock()
        app = MCPApp(name="test_app", upstream_session=mock_session)

        assert app._upstream_session is mock_session

    @pytest.mark.asyncio
    async def test_initialization_with_model_selector(self):
        """Test initialization with model selector."""
        mock_selector = MagicMock()
        app = MCPApp(name="test_app", model_selector=mock_selector)

        assert app._model_selector is mock_selector

    #
    # Windows Policy Tests
    #

    @pytest.mark.asyncio
    async def test_windows_event_loop_policy(self):
        """Test Windows event loop policy is set on Windows."""
        # Create a mock class to avoid importing WindowsProactorEventLoopPolicy
        # which doesn't exist on non-Windows platforms
        mock_policy_class = MagicMock()
        mock_policy_instance = MagicMock()
        mock_policy_class.return_value = mock_policy_instance

        # We need to patch the import of WindowsProactorEventLoopPolicy rather than patching asyncio directly
        import_patch = patch.dict(
            "sys.modules",
            {"asyncio": MagicMock(WindowsProactorEventLoopPolicy=mock_policy_class)},
        )
        platform_patch = patch("sys.platform", "win32")
        set_policy_patch = patch("asyncio.set_event_loop_policy")

        with import_patch, platform_patch, set_policy_patch as mock_set_policy:
            # Now create the app which should trigger the code path
            MCPApp(name="test_app")

            # Verify set_event_loop_policy was called
            mock_set_policy.assert_called_once()

    @pytest.mark.asyncio
    @patch("sys.platform", "linux")
    @patch("asyncio.set_event_loop_policy")
    async def test_non_windows_event_loop_policy(self, mock_set_policy):
        """Test Windows event loop policy is not set on non-Windows platforms."""
        MCPApp(name="test_app")

        mock_set_policy.assert_not_called()

    #
    # Context Management Tests
    #

    @pytest.mark.asyncio
    async def test_initialize_method(self, basic_app, mock_context):
        """Test initialize method."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ) as mock_init_context:
            await basic_app.initialize()

            assert basic_app._initialized is True
            assert basic_app._context is mock_context
            mock_init_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, basic_app, mock_context):
        """Test initialize method when already initialized."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ) as mock_init_context:
            # First initialization
            await basic_app.initialize()
            mock_init_context.reset_mock()

            # Second initialization
            await basic_app.initialize()

            # Should not call initialize_context again
            mock_init_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_method(self, basic_app, mock_context):
        """Test cleanup method."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            with patch("mcp_agent.app.cleanup_context", AsyncMock()) as mock_cleanup:
                await basic_app.initialize()
                await basic_app.cleanup()

                assert basic_app._initialized is False
                assert basic_app._context is None
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_not_initialized(self, basic_app):
        """Test cleanup method when not initialized."""
        with patch("mcp_agent.app.cleanup_context", AsyncMock()) as mock_cleanup:
            await basic_app.cleanup()

            # Should not call cleanup_context
            mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_context_manager(self, basic_app, mock_context):
        """Test run context manager."""
        basic_app._context = (
            mock_context  # Ensure context is set since initialize is mocked
        )
        with patch.object(basic_app, "initialize", AsyncMock()) as mock_init:
            with patch.object(basic_app, "cleanup", AsyncMock()) as mock_cleanup:
                async with basic_app.run() as running_app:
                    assert running_app is basic_app

                # Both methods should be called
                mock_init.assert_called_once()
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_context_manager_with_exception(self, basic_app, mock_context):
        """Test run context manager when an exception occurs."""
        basic_app._context = (
            mock_context  # Ensure context is set since initialize is mocked
        )
        with patch.object(basic_app, "initialize", AsyncMock()) as mock_init:
            with patch.object(basic_app, "cleanup", AsyncMock()) as mock_cleanup:
                try:
                    async with basic_app.run():
                        raise ValueError("Test exception")
                except ValueError:
                    pass

                # Both methods should be called
                mock_init.assert_called_once()
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_cancelled_cleanup(self, basic_app, mock_context):
        """Test run context manager when cleanup is cancelled."""
        basic_app._context = (
            mock_context  # Ensure context is set since initialize is mocked
        )
        with patch.object(basic_app, "initialize", AsyncMock()) as mock_init:
            # We need to handle the CancelledError inside the async context manager
            # by capturing it rather than letting it propagate
            mock_cleanup = AsyncMock(side_effect=asyncio.CancelledError())
            with patch.object(basic_app, "cleanup", mock_cleanup):
                try:
                    async with basic_app.run() as running_app:
                        assert running_app is basic_app
                except asyncio.CancelledError:
                    # We expect this exception and want to handle it in the test
                    pass

                # Both methods should be called
                mock_init.assert_called_once()
                mock_cleanup.assert_called_once()

    #
    # Property Access Tests
    #

    @pytest.mark.asyncio
    async def test_context_property_initialized(self, basic_app, mock_context):
        """Test context property when initialized."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert basic_app.context is mock_context

    @pytest.mark.asyncio
    async def test_context_property_not_initialized(self, basic_app):
        """Test context property when not initialized."""
        with pytest.raises(RuntimeError, match="MCPApp not initialized"):
            _ = basic_app.context

    @pytest.mark.asyncio
    async def test_config_property(self, basic_app, mock_context):
        """Test config property."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert isinstance(basic_app.config, Settings)

    @pytest.mark.asyncio
    async def test_server_registry_property(self, basic_app, mock_context):
        """Test server_registry property."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert basic_app.server_registry is mock_context.server_registry

    @pytest.mark.asyncio
    async def test_executor_property(self, basic_app, mock_context):
        """Test executor property."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert basic_app.executor is mock_context.executor

    @pytest.mark.asyncio
    async def test_engine_property(self, basic_app, mock_context):
        """Test engine property."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert basic_app.engine is mock_context.executor.execution_engine

    @pytest.mark.asyncio
    async def test_upstream_session_getter(self, basic_app, mock_context):
        """Test upstream_session getter."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            assert basic_app.upstream_session is mock_context.upstream_session

    @pytest.mark.asyncio
    async def test_upstream_session_setter(self, basic_app, mock_context):
        """Test upstream_session setter."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            new_session = MagicMock()
            basic_app.upstream_session = new_session

            assert mock_context.upstream_session is new_session

    @pytest.mark.asyncio
    async def test_workflows_property(self, basic_app):
        """Test workflows property."""
        assert basic_app.workflows is basic_app._workflows

    @pytest.mark.asyncio
    async def test_tasks_property(self, basic_app, mock_context):
        """Test tasks property."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            mock_context.task_registry.list_activities.return_value = ["task1", "task2"]
            await basic_app.initialize()

            assert basic_app.tasks == ["task1", "task2"]
            mock_context.task_registry.list_activities.assert_called_once()

    @pytest.mark.asyncio
    async def test_logger_property(self, basic_app):
        """Test logger property."""
        with patch("mcp_agent.app.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # First call creates the logger
            assert basic_app.logger is mock_logger
            mock_get_logger.assert_called_once_with(
                f"mcp_agent.{basic_app.name}", session_id=None
            )

            # Reset mock
            mock_get_logger.reset_mock()

            # Second call uses the existing logger
            assert basic_app.logger is mock_logger
            mock_get_logger.assert_not_called()

    @pytest.mark.asyncio
    async def test_logger_property_with_session_id(self, basic_app, mock_context):
        """Test logger property with session_id."""
        # First patch get_logger for the initialization
        with patch("mcp_agent.app.get_logger") as init_get_logger:
            # Return a mock logger for any initialization calls
            init_mock_logger = MagicMock()
            init_get_logger.return_value = init_mock_logger

            # Now initialize the context
            with patch(
                "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
            ):
                await basic_app.initialize()

            # Reset the logger to force recreation
            basic_app._logger = None

            # Now patch get_logger again for the actual test
            with patch("mcp_agent.app.get_logger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                # Get the logger - this should call get_logger with the session_id
                assert basic_app.logger is mock_logger
                mock_get_logger.assert_called_once_with(
                    f"mcp_agent.{basic_app.name}", session_id=mock_context.session_id
                )

    #
    # Workflow Registration Tests
    #

    @pytest.mark.asyncio
    async def test_workflow_decorator_default(
        self, basic_app, test_workflow, mock_context
    ):
        """Test workflow decorator default behavior."""
        # Set the context directly instead of patching the property
        basic_app._context = mock_context
        basic_app._initialized = True

        try:
            # Make sure decorator_registry.get_workflow_defn_decorator returns None for default path
            mock_context.decorator_registry.get_workflow_defn_decorator.return_value = (
                None
            )

            # No custom workflow_id
            decorated = basic_app.workflow(test_workflow)

            assert decorated is test_workflow  # Default is no-op
            assert hasattr(decorated, "_app")
            assert decorated._app is basic_app
            assert test_workflow.__name__ in basic_app.workflows
            assert basic_app.workflows[test_workflow.__name__] is test_workflow
        finally:
            # Reset the app state after the test
            basic_app._context = None
            basic_app._initialized = False

    @pytest.mark.asyncio
    async def test_workflow_decorator_with_id(
        self, basic_app, test_workflow, mock_context
    ):
        """Test workflow decorator with custom ID."""
        # Set the context directly instead of patching the property
        basic_app._context = mock_context
        basic_app._initialized = True

        try:
            # Make sure decorator_registry.get_workflow_defn_decorator returns None for default path
            mock_context.decorator_registry.get_workflow_defn_decorator.return_value = (
                None
            )

            # With custom workflow_id
            custom_id = "custom_workflow_id"
            decorated = basic_app.workflow(test_workflow, workflow_id=custom_id)

            assert decorated is test_workflow  # Default is no-op
            assert hasattr(decorated, "_app")
            assert decorated._app is basic_app
            assert custom_id in basic_app.workflows
            assert basic_app.workflows[custom_id] is test_workflow
        finally:
            # Reset the app state after the test
            basic_app._context = None
            basic_app._initialized = False

    @pytest.mark.asyncio
    async def test_workflow_decorator_with_engine(
        self, basic_app, test_workflow, mock_context
    ):
        """Test workflow decorator with execution engine."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Setup mock for workflow decorator
            mock_decorator = MagicMock()
            mock_decorator.return_value = "decorated_workflow"
            mock_context.decorator_registry.get_workflow_defn_decorator.return_value = (
                mock_decorator
            )

            # Call workflow decorator
            result = basic_app.workflow(test_workflow)

            # Verification
            assert result is test_workflow  # Should return the original class

    #
    # Workflow Run Tests
    #

    @pytest.mark.asyncio
    async def test_workflow_run_decorator_default(self, basic_app, mock_context):
        """Test workflow_run decorator default behavior."""
        # Set the context directly instead of patching the property
        basic_app._context = mock_context
        basic_app._initialized = True

        try:
            # Make sure decorator_registry.get_workflow_run_decorator returns None for default path
            mock_context.decorator_registry.get_workflow_run_decorator.return_value = (
                None
            )

            # Test function
            async def test_fn():
                return "test"

            # Default behavior is a no-op wrapper
            decorated = basic_app.workflow_run(test_fn)

            assert asyncio.iscoroutinefunction(decorated)

            # The wrapper itself is an async function
            assert asyncio.iscoroutinefunction(decorated)

            # Calling decorated() returns a coroutine object that we need to await
            result = await decorated()
            assert (
                result == "test"
            )  # Should still return the original function's return value
        finally:
            # Reset the app state after the test
            basic_app._context = None
            basic_app._initialized = False

    @pytest.mark.asyncio
    async def test_workflow_run_decorator_with_engine(self, basic_app, mock_context):
        """Test workflow_run decorator with execution engine."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Test function
            async def test_fn():
                return "test"

            # Setup mock for workflow run decorator
            mock_decorator = MagicMock()
            mock_decorator.return_value = "decorated_run"
            mock_context.decorator_registry.get_workflow_run_decorator.return_value = (
                mock_decorator
            )

            # Call workflow_run decorator
            result = basic_app.workflow_run(test_fn)

            # Verification
            assert asyncio.iscoroutinefunction(result)

    #
    # Task Registration Tests
    #

    @pytest.mark.asyncio
    async def test_workflow_task_decorator(self, basic_app, test_task, mock_context):
        """Test workflow_task decorator."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Call workflow_task decorator
            decorated = basic_app.workflow_task()(test_task)

            # Verification
            assert decorated is test_task  # Should return the original function
            assert hasattr(decorated, "is_workflow_task")
            assert decorated.is_workflow_task is True
            assert hasattr(decorated, "execution_metadata")
            assert (
                decorated.execution_metadata["activity_name"]
                == f"{test_task.__module__}.{test_task.__qualname__}"
            )

            # Verify task registration in the app's _task_registry
            activity_name = f"{test_task.__module__}.{test_task.__qualname__}"
            activities = basic_app._task_registry.list_activities()
            assert activity_name in activities
            registered_task = basic_app._task_registry.get_activity(activity_name)
            assert registered_task is decorated

    @pytest.mark.asyncio
    async def test_workflow_task_decorator_with_name(
        self, basic_app, test_task, mock_context
    ):
        """Test workflow_task decorator with custom name."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Call workflow_task decorator with custom name
            custom_name = "custom_task_name"
            decorated = basic_app.workflow_task(name=custom_name)(test_task)

            # Verification
            assert decorated.execution_metadata["activity_name"] == custom_name

            # Verify task registration in the app's _task_registry
            activities = basic_app._task_registry.list_activities()
            assert custom_name in activities
            registered_task = basic_app._task_registry.get_activity(custom_name)
            assert registered_task is decorated

    @pytest.mark.asyncio
    async def test_workflow_task_decorator_with_timeout(
        self, basic_app, test_task, mock_context
    ):
        """Test workflow_task decorator with custom timeout."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Call workflow_task decorator with custom timeout
            custom_timeout = timedelta(minutes=5)
            decorated = basic_app.workflow_task(
                schedule_to_close_timeout=custom_timeout
            )(test_task)

            # Verification
            assert (
                decorated.execution_metadata["schedule_to_close_timeout"]
                == custom_timeout
            )

            # Verify task registration in the app's _task_registry
            activity_name = decorated.execution_metadata["activity_name"]
            activities = basic_app._task_registry.list_activities()
            assert activity_name in activities
            registered_task = basic_app._task_registry.get_activity(activity_name)
            assert registered_task is decorated
            assert (
                registered_task.execution_metadata["schedule_to_close_timeout"]
                == custom_timeout
            )

    @pytest.mark.asyncio
    async def test_workflow_task_decorator_with_retry_policy(
        self, basic_app, test_task, mock_context
    ):
        """Test workflow_task decorator with custom retry policy."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Call workflow_task decorator with custom retry policy
            retry_policy = {"max_attempts": 3, "backoff_coefficient": 2.0}
            decorated = basic_app.workflow_task(retry_policy=retry_policy)(test_task)

            # Verification
            assert decorated.execution_metadata["retry_policy"] == retry_policy

            # Verify task registration in the app's _task_registry
            activity_name = decorated.execution_metadata["activity_name"]
            activities = basic_app._task_registry.list_activities()
            assert activity_name in activities
            registered_task = basic_app._task_registry.get_activity(activity_name)
            assert registered_task is decorated
            assert registered_task.execution_metadata["retry_policy"] == retry_policy

    @pytest.mark.asyncio
    async def test_workflow_task_with_non_async_function(self, basic_app):
        """Test workflow_task with non-async function."""

        # Non-async function
        def non_async_fn(param):
            return f"Result: {param}"

        # Should raise TypeError
        with pytest.raises(TypeError, match="must be async"):
            basic_app.workflow_task()(non_async_fn)

    @pytest.mark.asyncio
    async def test_is_workflow_task_method(self, basic_app, test_task, mock_context):
        """Test is_workflow_task method."""
        with patch(
            "mcp_agent.app.initialize_context", AsyncMock(return_value=mock_context)
        ):
            await basic_app.initialize()

            # Not a workflow task initially
            assert basic_app.is_workflow_task(test_task) is False

            # Mark as workflow task
            decorated = basic_app.workflow_task()(test_task)

            # Now should be a workflow task
            assert basic_app.is_workflow_task(decorated) is True
