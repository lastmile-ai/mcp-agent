import functools
from types import MethodType
from typing import Any, Dict, Optional, Type, TypeVar, Callable, TYPE_CHECKING
from datetime import timedelta
import asyncio
import sys
from contextlib import asynccontextmanager
from opentelemetry import trace

from mcp import ServerSession
from mcp_agent.core.context import Context, initialize_context, cleanup_context
from mcp_agent.config import Settings, get_settings
from mcp_agent.executor.signal_registry import SignalRegistry
from mcp_agent.logging.event_progress import ProgressAction
from mcp_agent.logging.logger import get_logger
from mcp_agent.executor.decorator_registry import (
    DecoratorRegistry,
    register_asyncio_decorators,
    register_temporal_decorators,
)
from mcp_agent.executor.task_registry import ActivityRegistry
from mcp_agent.executor.workflow_signal import SignalWaitCallback
from mcp_agent.executor.workflow_task import GlobalWorkflowTaskRegistry
from mcp_agent.human_input.types import HumanInputCallback
from mcp_agent.utils.common import unwrap
from mcp_agent.workflows.llm.llm_selector import ModelSelector

if TYPE_CHECKING:
    from mcp_agent.agents.agent_config import AgentConfig
    from mcp_agent.executor.workflow import Workflow

R = TypeVar("R")


class MCPApp:
    """
    Main application class that manages global state and can host workflows.

    Example usage:
        app = MCPApp()

        @app.workflow
        class MyWorkflow(Workflow[str]):
            @app.task
            async def my_task(self):
                pass

            async def run(self):
                await self.my_task()

        async with app.run() as running_app:
            workflow = MyWorkflow()
            result = await workflow.execute()
    """

    def __init__(
        self,
        name: str = "mcp_application",
        description: str | None = None,
        settings: Optional[Settings] | str = None,
        human_input_callback: Optional[HumanInputCallback] = None,
        signal_notification: Optional[SignalWaitCallback] = None,
        upstream_session: Optional["ServerSession"] = None,
        model_selector: ModelSelector = None,
    ):
        """
        Initialize the application with a name and optional settings.
        Args:
            name: Name of the application
            description: Description of the application. If you expose the MCPApp as an MCP server,
                provide a detailed description, since it will be used as the server's description.
            settings: Application configuration - If unspecified, the settings are loaded from mcp_agent.config.yaml.
                If this is a string, it is treated as the path to the config file to load.
            human_input_callback: Callback for handling human input
            signal_notification: Callback for getting notified on workflow signals/events.
            upstream_session: Upstream session if the MCPApp is running as a server to an MCP client.
            initialize_model_selector: Initializes the built-in ModelSelector to help with model selection. Defaults to False.
        """
        self.name = name
        self.description = description or "MCP Agent Application"

        # We use these to initialize the context in initialize()
        if settings is None:
            self._config = get_settings()
        elif isinstance(settings, str):
            self._config = get_settings(config_path=settings)
        else:
            self._config = settings

        # We initialize the task and decorator registries at construction time
        # (prior to initializing the context) to ensure that they are available
        # for any decorators that are applied to the workflow or task methods.
        self._task_registry = ActivityRegistry()
        self._decorator_registry = DecoratorRegistry()
        self._signal_registry = SignalRegistry()
        register_asyncio_decorators(self._decorator_registry)
        register_temporal_decorators(self._decorator_registry)
        self._registered_global_workflow_tasks = set()

        self._human_input_callback = human_input_callback
        self._signal_notification = signal_notification
        self._upstream_session = upstream_session
        self._model_selector = model_selector

        self._workflows: Dict[str, Type["Workflow"]] = {}  # id to workflow class

        self._agent_configs: Dict[
            str, "AgentConfig"
        ] = {}  # name to agent configuration

        self._logger = None
        self._context: Optional[Context] = None
        self._initialized = False

        try:
            # Set event loop policy for Windows
            if sys.platform == "win32":
                import asyncio

                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        finally:
            pass

    @property
    def context(self) -> Context:
        if self._context is None:
            raise RuntimeError(
                "MCPApp not initialized, please call initialize() first, or use async with app.run()."
            )
        return self._context

    @property
    def config(self):
        return self._config

    @property
    def server_registry(self):
        return self._context.server_registry

    @property
    def executor(self):
        return self._context.executor

    @property
    def engine(self):
        return self.executor.execution_engine

    @property
    def upstream_session(self):
        return self._context.upstream_session

    @upstream_session.setter
    def upstream_session(self, value):
        self._context.upstream_session = value

    @property
    def workflows(self):
        return self._workflows

    @property
    def tasks(self):
        return self.context.task_registry.list_activities()

    @property
    def session_id(self):
        return self.context.session_id

    @property
    def logger(self):
        if self._logger is None:
            session_id = self._context.session_id if self._context else None
            self._logger = get_logger(f"mcp_agent.{self.name}", session_id=session_id)
        return self._logger

    async def initialize(self):
        """Initialize the application."""
        if self._initialized:
            return

        # Pass the session ID to initialize_context
        self._context = await initialize_context(
            config=self.config,
            task_registry=self._task_registry,
            decorator_registry=self._decorator_registry,
            signal_registry=self._signal_registry,
            store_globally=True,
        )

        # Set the properties that were passed in the constructor
        self._context.human_input_handler = self._human_input_callback
        self._context.signal_notification = self._signal_notification
        self._context.upstream_session = self._upstream_session
        self._context.model_selector = self._model_selector

        # Store a reference to this app instance in the context for easier access
        self._context.app = self

        self._register_global_workflow_tasks()

        self._initialized = True
        self.logger.info(
            "MCPAgent initialized",
            data={
                "progress_action": "Running",
                "target": self.name,
                "agent_name": "mcp_application_loop",
                "session_id": self.session_id,
            },
        )

    async def cleanup(self):
        """Cleanup application resources."""
        if not self._initialized:
            return

        # Updatre progress display before logging is shut down
        self.logger.info(
            "MCPAgent cleanup",
            data={
                "progress_action": ProgressAction.FINISHED,
                "target": self.name or "mcp_app",
                "agent_name": "mcp_application_loop",
            },
        )

        try:
            await cleanup_context()
        except asyncio.CancelledError:
            self.logger.debug("Cleanup cancelled during shutdown")

        self._context = None
        self._initialized = False

    @asynccontextmanager
    async def run(self):
        """
        Run the application. Use as context manager.

        Example:
            async with app.run() as running_app:
                # App is initialized here
                pass
        """
        await self.initialize()

        tracer = self.context.tracer or trace.get_tracer("mcp-agent")
        with tracer.start_as_current_span(self.name):
            try:
                yield self
            finally:
                await self.cleanup()

    def workflow(
        self, cls: Type, *args, workflow_id: str | None = None, **kwargs
    ) -> Type:
        """
        Decorator for a workflow class. By default it's a no-op,
        but different executors can use this to customize behavior
        for workflow registration.

        Example:
            If Temporal is available & we use a TemporalExecutor,
            this decorator will wrap with temporal_workflow.defn.
        """
        cls._app = self

        workflow_id = workflow_id or cls.__name__

        # Apply the engine-specific decorator if available
        engine_type = self.config.execution_engine
        workflow_defn_decorator = self._decorator_registry.get_workflow_defn_decorator(
            engine_type
        )

        if workflow_defn_decorator:
            # TODO: jerron - Setting sandboxed=False is a workaround to silence temporal's RestrictedWorkflowAccessError.
            # Can we make this work without having to run outside sandbox environment?
            # This is not ideal as it could lead to non-deterministic behavior.
            decorated_cls = workflow_defn_decorator(
                cls, sandboxed=False, *args, **kwargs
            )
            self._workflows[workflow_id] = decorated_cls
            return decorated_cls
        else:
            self._workflows[workflow_id] = cls
            return cls

    def workflow_signal(self, fn: Callable[..., R]) -> Callable[..., R]:
        """
        Decorator for a workflow's signal handler.
        Different executors can use this to customize behavior for workflow signal handling.

        Example:
            If Temporal is in use, this gets converted to @workflow.signal.
        """
        # Apply the engine-specific decorator if available
        engine_type = self.config.execution_engine
        signal_decorator = self._decorator_registry.get_workflow_signal_decorator(
            engine_type
        )

        # TODO: jerron - use a unique name in the event of multiple similar workflows.
        decorated_fn = (
            signal_decorator(fn, name=fn.__name__) if signal_decorator else fn
        )

        @functools.wraps(decorated_fn)
        async def wrapper(*args, **kwargs):
            signal_handler_args = args[1:]
            return decorated_fn(*signal_handler_args, **kwargs)

        self._signal_registry.register(
            fn.__name__, wrapper, state={"completed": False, "value": None}
        )

        return wrapper

    def workflow_run(self, fn: Callable[..., R], **kwargs) -> Callable[..., R]:
        """
        Decorator for a workflow's main 'run' method.
        Different executors can use this to customize behavior for workflow execution.

        Example:
            If Temporal is in use, this gets converted to @workflow.run.
        """
        # Apply the engine-specific decorator if available
        engine_type = self.config.execution_engine
        run_decorator = self._decorator_registry.get_workflow_run_decorator(engine_type)
        decorated_fn = run_decorator(fn, **kwargs) if run_decorator else fn

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not args:
                return await decorated_fn(*args, **kwargs)

            # Get the workflow class instance from the first argument
            instance = args[0]
            workflow_cls = instance.__class__
            method_name = fn.__name__

            # See if we need to store the decorated method on the class
            # (we only need to do this once per class)
            if run_decorator and not hasattr(workflow_cls, f"_decorated_{method_name}"):
                setattr(workflow_cls, f"_decorated_{method_name}", decorated_fn)

            # Use the decorated method if available on the class
            class_decorated = getattr(workflow_cls, f"_decorated_{method_name}", None)
            if class_decorated:
                return await class_decorated(*args, **kwargs)

            # Fall back to the original function
            return await fn(*args, **kwargs)

        return wrapper

    def workflow_task(
        self,
        name: str | None = None,
        schedule_to_close_timeout: timedelta | None = None,
        retry_policy: Dict[str, Any] | None = None,
        **meta_kwargs,
    ) -> Callable[[Callable[..., R]], Callable[..., R]]:
        """
        Decorator to mark a function as a workflow task,
        automatically registering it in the global activity registry.

        Args:
            name: Optional custom name for the activity
            schedule_to_close_timeout: Maximum time the task can take to complete
            retry_policy: Retry policy configuration
            **kwargs: Additional metadata passed to the activity registration

        Returns:
            Decorated function that preserves async and typing information

        Raises:
            TypeError: If the decorated function is not async
            ValueError: If the retry policy or timeout is invalid
        """

        def decorator(target: Callable[..., R]) -> Callable[..., R]:
            func = unwrap(target)  # underlying function

            if not asyncio.iscoroutinefunction(func):
                raise TypeError(f"{func.__qualname__} must be async")

            activity_name = name or f"{func.__module__}.{func.__qualname__}"
            metadata = {
                "activity_name": activity_name,
                "schedule_to_close_timeout": schedule_to_close_timeout
                or timedelta(minutes=10),
                "retry_policy": retry_policy or {},
                **meta_kwargs,
            }

            # bookkeeping that survives partial/bound wrappers
            func.is_workflow_task = True
            func.execution_metadata = metadata

            task_defn = self._decorator_registry.get_workflow_task_decorator(
                self.config.execution_engine
            )

            if task_defn:
                if isinstance(target, MethodType):
                    self_ref = target.__self__

                    @functools.wraps(func)
                    async def _bound_adapter(*a, **k):
                        return await func(self_ref, *a, **k)

                    _bound_adapter.__annotations__ = func.__annotations__.copy()
                    task_callable = task_defn(_bound_adapter, name=activity_name)
                else:
                    task_callable = task_defn(func, name=activity_name)
            else:
                task_callable = target  # asyncio backend

            # ---- register *after* decorating --------------------------------
            self._task_registry.register(activity_name, task_callable, metadata)

            # Return the callable we created rather than re-decorating
            return task_callable

        return decorator

    def is_workflow_task(self, func: Callable[..., Any]) -> bool:
        """
        Check if a function is marked as a workflow task.
        This gets set for functions that are decorated with @workflow_task."""
        return bool(getattr(func, "is_workflow_task", False))

    @property
    def agent_configs(self) -> Dict[str, "AgentConfig"]:
        """Get the dictionary of registered agent configurations."""
        return self._agent_configs

    def register_agent_config(self, config: "AgentConfig") -> "AgentConfig":
        """
        Register an agent configuration with the application.

        Args:
            config: The agent configuration to register

        Returns:
            The registered configuration
        """
        self._agent_configs[config.name] = config
        return config

    def _register_global_workflow_tasks(self):
        """Register all statically defined workflow tasks with this app instance."""
        registry = GlobalWorkflowTaskRegistry()

        self.logger.debug(
            "Registering global workflow tasks with application instance."
        )

        for target, metadata in registry.get_all_tasks():
            func = unwrap(target)  # underlying function
            activity_name = metadata["activity_name"]

            self.logger.debug(f"Registering global workflow task: {activity_name}")

            # Skip if already registered in this app instance
            if activity_name in self._registered_global_workflow_tasks:
                self.logger.debug(
                    f"Global workflow task {activity_name} already registered, skipping."
                )
                continue

            # Skip if already registered in the app's task registry
            if activity_name in self._task_registry.list_activities():
                self.logger.debug(
                    f"Global workflow task {activity_name} already registered in task registry, skipping."
                )
                self._registered_global_workflow_tasks.add(activity_name)
                continue

            # Apply the engine-specific decorator if available
            task_defn = self._decorator_registry.get_workflow_task_decorator(
                self.config.execution_engine
            )

            if task_defn:  # Engine-specific decorator available
                if isinstance(target, MethodType):
                    self_ref = target.__self__

                    @functools.wraps(func)
                    async def _bound_adapter(*a, **k):
                        return await func(self_ref, *a, **k)

                    _bound_adapter.__annotations__ = func.__annotations__.copy()
                    task_callable = task_defn(_bound_adapter, name=activity_name)
                else:
                    task_callable = task_defn(func, name=activity_name)
            else:
                task_callable = target  # asyncio backend

            # Register with the task registry
            self._task_registry.register(activity_name, task_callable, metadata)

            # Mark as registered in this app instance
            self._registered_global_workflow_tasks.add(activity_name)
