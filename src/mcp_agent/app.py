import asyncio
import os
import sys
import functools

from types import MethodType, FunctionType
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Callable,
    TYPE_CHECKING,
    ParamSpec,
    overload,
)
from datetime import timedelta
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from mcp import ServerSession
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations, Icon
from mcp_agent.core.context import Context, initialize_context, cleanup_context
from mcp_agent.config import Settings, WorkflowTaskRetryPolicy, get_settings
from mcp_agent.executor.signal_registry import SignalRegistry
from mcp_agent.logging.event_progress import ProgressAction
from mcp_agent.logging.logger import get_logger
from mcp_agent.logging.logger import set_default_bound_context
from mcp_agent.executor.decorator_registry import (
    DecoratorRegistry,
    register_asyncio_decorators,
    register_temporal_decorators,
)
from mcp_agent.executor.task_registry import ActivityRegistry
from mcp_agent.executor.workflow_signal import SignalWaitCallback
from mcp_agent.executor.workflow_task import GlobalWorkflowTaskRegistry
from mcp_agent.human_input.types import HumanInputCallback
from mcp_agent.elicitation.types import ElicitationCallback
from mcp_agent.server.tool_adapter import validate_tool_schema
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.utils.common import unwrap
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from mcp_agent.oauth.manager import TokenManager
from mcp_agent.oauth.store import InMemoryTokenStore
from mcp_agent.workflows.factory import load_agent_specs_from_dir


if TYPE_CHECKING:
    from mcp_agent.agents.agent_spec import AgentSpec
    from mcp_agent.executor.workflow import Workflow

P = ParamSpec("P")
R = TypeVar("R")

phetch = Icon(
    src="https://s3.us-east-1.amazonaws.com/publicdata.lastmileai.com/phetch.png",
    mimeType="image/png",
    sizes=["48x48"],
)


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
        settings: Settings | str | None = None,
        mcp: FastMCP | None = None,
        human_input_callback: HumanInputCallback | None = None,
        elicitation_callback: ElicitationCallback | None = None,
        signal_notification: SignalWaitCallback | None = None,
        upstream_session: Optional["ServerSession"] = None,
        model_selector: ModelSelector | None = None,
        icons: list[Icon] | None = None,
        session_id: str | None = None,
    ):
        """
        Initialize the application with a name and optional settings.
        Args:
            name: Name of the application
            description: Description of the application. If you expose the MCPApp as an MCP server,
                provide a detailed description, since it will be used as the server's description.
            settings: Application configuration - If unspecified, the settings are loaded from mcp_agent.config.yaml.
                If this is a string, it is treated as the path to the config file to load.
            mcp: MCP server instance to use for the application to expose agents and workflows as tools.
                If not provided, a default FastMCP server will be created by create_mcp_server_for_app().
                If provided, the MCPApp will add tools to the provided server instance.
            human_input_callback: Callback for handling human input
            signal_notification: Callback for getting notified on workflow signals/events.
            upstream_session: Upstream session if the MCPApp is running as a server to an MCP client.
            initialize_model_selector: Initializes the built-in ModelSelector to help with model selection. Defaults to False.
        """
        self.mcp = mcp

        # We use these to initialize the context in initialize()
        if settings is None:
            self._config = get_settings()
        elif isinstance(settings, str):
            self._config = get_settings(config_path=settings)
        else:
            self._config = settings

        self.name = name or self._config.name or (mcp.name if mcp else None)

        self.description = (
            description
            or self._config.description
            or (mcp.instructions if mcp else "MCP Agent Application")
        )

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
        self._elicitation_callback = elicitation_callback
        self._signal_notification = signal_notification
        self._upstream_session = upstream_session
        self._model_selector = model_selector
        if icons:
            self._icons = icons
        else:
            self._icons = [phetch]
        self._session_id_override = session_id

        self._workflows: Dict[str, Type["Workflow"]] = {}  # id to workflow class
        # Deferred tool declarations to register with MCP server when available
        # Each entry: {
        #   "name": str,
        #   "mode": "sync" | "async",
        #   "workflow_name": str,
        #   "workflow_cls": Type[Workflow],
        #   "tool_wrapper": Callable | None,
        #   "structured_output": bool | None,
        #   "description": str | None,
        # }
        self._declared_tools: list[dict[str, Any]] = []

        self._logger = None
        self._context: Optional[Context] = None
        self._initialized = False
        self._tracer_provider = None
        self._dotenv_loaded = False

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
            # Do not pass context kwarg to match expected call signature in tests
            self._logger = get_logger(f"mcp_agent.{self.name}", session_id=session_id)
            # Bind context for upstream forwarding and other contextual logging
            try:
                if self._context is not None:
                    self._logger._bound_context = self._context  # type: ignore[attr-defined]

            except Exception:
                pass
        else:
            # Update the logger's bound context in case upstream_session was set after logger creation
            if self._context and hasattr(self._logger, "_bound_context"):
                self._logger._bound_context = self._context

        return self._logger

    def _apply_environment_bindings(self) -> None:
        """Populate os.environ with values declared in settings.env when the value is available."""

        self._load_dotenv_files()

        try:
            specs = list(self._config.iter_env_specs())
        except Exception:
            return

        for key, value in specs:
            if not key:
                continue
            if value is None:
                continue
            str_value = str(value)
            if str_value.startswith("mcpac_sc_"):
                # Actual secret values are injected by the deployment environment; skip handles.
                continue
            os.environ[key] = str_value

    def _load_dotenv_files(self) -> None:
        if self._dotenv_loaded:
            return
        try:
            load_dotenv(dotenv_path=".env", override=False)
        except Exception:
            pass
        try:
            load_dotenv(dotenv_path=".env.mcp-cloud", override=False)
        except Exception:
            pass
        self._dotenv_loaded = True

    async def initialize(self):
        """Initialize the application."""
        if self._initialized:
            return

        self._apply_environment_bindings()

        # Pass the session ID to initialize_context
        self._context = await initialize_context(
            config=self.config,
            task_registry=self._task_registry,
            decorator_registry=self._decorator_registry,
            signal_registry=self._signal_registry,
            store_globally=True,
            session_id=self._session_id_override,
        )

        # Store the app-specific tracer provider
        if self._context.tracing_enabled and self._context.tracing_config:
            self._tracer_provider = self._context.tracing_config._tracer_provider

        # Set the properties that were passed in the constructor
        self._context.human_input_handler = self._human_input_callback
        self._context.elicitation_handler = self._elicitation_callback
        self._context.signal_notification = self._signal_notification
        self._context.upstream_session = self._upstream_session
        self._context.model_selector = self._model_selector

        # Store a reference to this app instance in the context for easier access
        self._context.app = self

        # Initialize OAuth token management helpers if configured
        oauth_settings = None
        try:
            if self._context.config:
                oauth_settings = self._context.config.oauth
        except Exception:
            oauth_settings = None

        if oauth_settings:
            self.logger.debug("Initializing OAuth token management")
            backend = (
                oauth_settings.token_store.backend
                if oauth_settings.token_store
                else "memory"
            )
            if backend == "redis":
                from mcp_agent.oauth.store import RedisTokenStore

                if RedisTokenStore is None:
                    raise ImportError(
                        "Redis token store requires the 'redis' optional dependency. "
                        "Install with `pip install mcp-agent[redis]`."
                    )

                redis_url = oauth_settings.token_store.redis_url
                if not redis_url:
                    raise ValueError(
                        "redis_url must be configured when using the Redis token store"
                    )
                token_store = RedisTokenStore(
                    url=redis_url,
                    prefix=oauth_settings.token_store.redis_prefix,
                )
            else:
                token_store = InMemoryTokenStore()

            token_manager = TokenManager(
                token_store=token_store,
                settings=oauth_settings,
            )
            self._context.token_store = token_store
            self._context.token_manager = token_manager

            # Check for pre-configured tokens and store them with synthetic users
            await self._initialize_preconfigured_tokens(token_manager)
        else:
            self.logger.debug("No OAuth settings found, skipping OAuth initialization")

        # Provide a safe default bound context for loggers created after init without explicit context
        try:
            set_default_bound_context(self._context)
        except Exception:
            pass

        # Auto-load subagents if enabled in settings
        try:
            subagents = self._config.agents

            if subagents is not None and subagents.enabled:
                self.logger.info("Loading subagents from configuration...")

                # Enforce precedence and deduplicate by name:
                # - Inline definitions (highest precedence)
                # - search_paths in given order (earlier has higher precedence)
                loaded_by_name: Dict[str, "AgentSpec"] = {}

                # Process search paths from lowest to highest precedence so that
                # higher precedence can overwrite lower ones while logging a warning.
                for p in reversed(subagents.search_paths or []):
                    path = os.path.expanduser(p)
                    agents_from_search_path = load_agent_specs_from_dir(
                        path=path, pattern=subagents.pattern, context=self._context
                    )

                    if agents_from_search_path:
                        self.logger.info(
                            f"Found subagents in {path}",
                            data={"count": len(agents_from_search_path)},
                        )
                        for spec in agents_from_search_path:
                            if spec.name in loaded_by_name:
                                self.logger.warning(
                                    "Duplicate subagent name encountered; overwriting with higher-precedence definition",
                                    data={"agent_name": spec.name, "source": path},
                                )
                            loaded_by_name[spec.name] = spec

                # Inline subagents (highest precedence): overwrite if duplicate
                for spec in subagents.definitions or []:
                    if spec.name in loaded_by_name:
                        self.logger.warning(
                            "Duplicate subagent name encountered; overwriting with inline definition",
                            data={"agent_name": spec.name},
                        )
                    loaded_by_name[spec.name] = spec

                if loaded_by_name:
                    # Keep the loaded specs on context for access by workflows/factories
                    self._context.loaded_subagents = list(loaded_by_name.values())
                    self.logger.info(
                        "Loaded subagents",
                        data={
                            "count": len(self._context.loaded_subagents),
                            "agents": [
                                spec.name for spec in self._context.loaded_subagents
                            ],
                        },
                    )
        except Exception as e:
            # Non-fatal: log and continue
            self.logger.warning(f"Subagent discovery failed: {e}")

        self._register_global_workflow_tasks()

        self._initialized = True
        self.logger.info(
            "MCPApp initialized",
            data={
                "progress_action": "Running",
                "target": self.name,
                "agent_name": "mcp_application_loop",
                "session_id": self.session_id,
            },
        )

    async def _initialize_preconfigured_tokens(self, token_manager):
        """Check for pre-configured OAuth tokens and store them with a single synthetic user."""

        mcp_config = getattr(self._context.config, "mcp", None)
        if not mcp_config or not getattr(mcp_config, "servers", None):
            self.logger.debug(
                "No MCP servers found in config, skipping token initialization"
            )
            return

        servers = mcp_config.servers
        self.logger.debug(f"Found MCP servers in config: {list(servers.keys())}")

        servers_with_tokens = []

        # First pass: check which servers have pre-configured tokens
        for server_name, server_config in servers.items():
            if not hasattr(server_config, "auth") or not server_config.auth:
                self.logger.debug(
                    f"Server '{server_name}' has no auth config, skipping"
                )
                continue

            oauth_config = getattr(server_config.auth, "oauth", None)

            if (
                not oauth_config
                or not oauth_config.enabled
                or not oauth_config.access_token
            ):
                continue

            self.logger.debug(f"Server '{server_name}' has pre-configured OAuth token")
            servers_with_tokens.append((server_name, server_config))

        if servers_with_tokens:
            for server_name, server_config in servers_with_tokens:
                self.logger.info(
                    "Storing pre-configured OAuth token for server: %s", server_name
                )
                await token_manager.store_preconfigured_token(
                    context=self._context,
                    server_name=server_name,
                    server_config=server_config,
                )

    async def get_token_node(self):
        """Return the root app token node, if available."""
        if not self._context or not getattr(self._context, "token_counter", None):
            return None
        return await self._context.token_counter.get_app_node()

    async def get_token_usage(self):
        """Return total token usage across the app (root node)."""
        if not self._context or not getattr(self._context, "token_counter", None):
            return None
        node = await self.get_token_node()
        return node.get_usage() if node else None

    async def get_token_summary(self):
        """Return TokenSummary across the entire app."""
        if not self._context or not getattr(self._context, "token_counter", None):
            return None
        # Keep summary for model breakdowns while delegating node-sourced methods elsewhere
        return await self._context.token_counter.get_summary()

    async def watch_tokens(
        self,
        callback,
        *,
        threshold: int | None = None,
        throttle_ms: int | None = None,
        include_subtree: bool = True,
    ) -> str | None:
        """Watch the root app token usage. Returns a watch_id or None if not available."""
        node = await self.get_token_node()
        if not node:
            return None
        return await node.watch(
            callback,
            threshold=threshold,
            throttle_ms=throttle_ms,
            include_subtree=include_subtree,
        )

    async def format_token_tree(self) -> str:
        node = await self.get_token_node()
        if not node:
            return "(no token usage)"
        return node.format_tree()

    async def cleanup(self):
        """Cleanup application resources."""
        if not self._initialized:
            return

        # Updatre progress display before logging is shut down
        self.logger.info(
            "MCPApp cleanup",
            data={
                "progress_action": ProgressAction.FINISHED,
                "target": self.name or "mcp_app",
                "agent_name": "mcp_application_loop",
            },
        )

        # Force flush traces before cleanup
        if self._context and self._context.tracing_config:
            await self._context.tracing_config.flush()

        try:
            # Don't shutdown OTEL completely, just cleanup app-specific resources
            await cleanup_context(shutdown_logger=False)
        except asyncio.CancelledError:
            self.logger.debug("Cleanup cancelled during shutdown")

        # Shutdown the tracer provider to stop background threads
        # This prevents dangling span exports after cleanup
        if self._context and self._context.tracing_config:
            self._context.tracing_config.shutdown()

        self._context = None
        self._initialized = False
        self._tracer_provider = None

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

        # Push token tracking context for the app
        if self.context.token_counter:
            await self.context.token_counter.push(name=self.name, node_type="app")

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(self.name):
            try:
                yield self
            finally:
                # Pop token tracking context
                if self.context.token_counter:
                    await self.context.token_counter.pop()
                await self.cleanup()

    def workflow(
        self,
        cls: Type,
        *args,
        workflow_id: str | None = None,
        retry_policy: WorkflowTaskRetryPolicy | Dict[str, Any] | None = None,
        **kwargs,
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
        normalized_retry_policy = self._normalize_workflow_retry_policy(retry_policy)
        if normalized_retry_policy is not None:
            setattr(cls, "_workflow_retry_policy", normalized_retry_policy)

        workflow_id = workflow_id or cls.__name__

        # Apply the engine-specific decorator if available
        engine_type = self.config.execution_engine
        workflow_defn_decorator = self._decorator_registry.get_workflow_defn_decorator(
            engine_type
        )

        if workflow_defn_decorator:
            # TODO: jerron (MAC) - Setting sandboxed=False is a workaround to silence temporal's RestrictedWorkflowAccessError.
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

    def workflow_signal(
        self, fn: Callable[..., R] | None = None, *, name: str | None = None
    ) -> Callable[..., R]:
        """
        Decorator for a workflow's signal handler.
        Different executors can use this to customize behavior for workflow signal handling.

        Args:
            fn: The function to decorate (optional, for use with direct application)
            name: Optional custom name for the signal. If not provided, uses the function name.

        Example:
            If Temporal is in use, this gets converted to @workflow.signal.
        """

        def decorator(func):
            # Determine the signal name to use
            signal_name = name or func.__name__

            # Get the engine-specific signal decorator
            engine_type = self.config.execution_engine
            signal_decorator = self._decorator_registry.get_workflow_signal_decorator(
                engine_type
            )

            # Apply the engine-specific decorator if available
            # Important: We need to correctly pass the name parameter to the Temporal decorator
            if signal_decorator:
                # For Temporal, ensure we're passing name as a keyword argument
                decorated_fn = signal_decorator(name=signal_name)(func)
            else:
                decorated_fn = func

            @functools.wraps(decorated_fn)
            async def wrapper(*args, **kwargs):
                signal_handler_args = args[1:]
                return decorated_fn(*signal_handler_args, **kwargs)

            # Register with the signal registry using the custom name
            self._signal_registry.register(
                signal_name, wrapper, state={"completed": False, "value": None}
            )

            return wrapper

        # Handle both @app.workflow_signal and @app.workflow_signal(name="custom_name")
        if fn is None:
            return decorator
        return decorator(fn)

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

            # Ensure initialization happens
            await instance.initialize()

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

        # Ensure the wrapper shares the original function's globals so that
        # string annotations (from __future__ import annotations) continue to
        # resolve against the workflow module rather than mcp_agent.app.
        original_globals = getattr(fn, "__globals__", None)
        if original_globals is not None and wrapper.__globals__ is not original_globals:
            rebuilt_wrapper = FunctionType(
                wrapper.__code__,
                original_globals,
                name=wrapper.__name__,
                argdefs=wrapper.__defaults__,
                closure=wrapper.__closure__,
            )
            rebuilt_wrapper.__kwdefaults__ = wrapper.__kwdefaults__
            rebuilt_wrapper.__annotations__ = wrapper.__annotations__
            rebuilt_wrapper.__dict__.update(wrapper.__dict__)
            rebuilt_wrapper = functools.update_wrapper(rebuilt_wrapper, fn)
            rebuilt_wrapper.__wrapped__ = fn
            wrapper = rebuilt_wrapper

        return wrapper

    def _create_workflow_from_function(
        self,
        fn: Callable[..., Any],
        *,
        workflow_name: str,
        description: str | None = None,
        mark_sync_tool: bool = False,
    ) -> Type:
        """
        Create a Workflow subclass dynamically from a plain function.

        The generated workflow class will:
        - Have `run` implemented to call the provided function
        - Be decorated with engine-specific run decorators via workflow_run
        - Expose the original function for parameter schema generation
        """

        import asyncio as _asyncio
        from mcp_agent.executor.workflow import Workflow as _Workflow

        async def _invoke_target(workflow_self, *args, **kwargs):
            # Inject app_ctx (AppContext) and shim ctx (FastMCP Context) if requested by the function
            import inspect as _inspect
            import typing as _typing

            call_kwargs = dict(kwargs)

            # If Temporal passed a single positional dict payload, merge into kwargs
            if len(args) == 1 and isinstance(args[0], dict):
                try:
                    call_kwargs = {**args[0], **call_kwargs}
                    args = ()
                except Exception:
                    pass

            # Detect if function expects an AppContext parameter (named 'app_ctx' or annotated with our Context)
            try:
                sig = _inspect.signature(fn)
                app_context_param_name = None

                for param_name, param in sig.parameters.items():
                    if param_name == "app_ctx":
                        app_context_param_name = param_name
                        break
                    if param.annotation != _inspect.Parameter.empty:
                        ann_str = str(param.annotation)
                        if "mcp_agent.core.context.Context" in ann_str:
                            app_context_param_name = param_name
                            break
                # If requested, inject the workflow's context (use property for fallback)
                if app_context_param_name:
                    try:
                        _ctx_obj = workflow_self.context
                    except Exception:
                        _ctx_obj = getattr(workflow_self, "_context", None)
                    if _ctx_obj is not None:
                        call_kwargs[app_context_param_name] = _ctx_obj
            except Exception:
                pass

            # If the function expects a FastMCP Context (ctx/context), ensure it's present.
            try:
                from mcp.server.fastmcp import Context as _Ctx  # type: ignore
            except Exception:
                _Ctx = None  # type: ignore

            def _is_fast_ctx_annotation(annotation) -> bool:
                if _Ctx is None or annotation is _inspect._empty:
                    return False
                if annotation is _Ctx:
                    return True
                if _inspect.isclass(annotation):
                    try:
                        if issubclass(annotation, _Ctx):  # type: ignore[misc]
                            return True
                    except TypeError:
                        pass
                try:
                    origin = _typing.get_origin(annotation)
                    if origin is not None:
                        return any(
                            _is_fast_ctx_annotation(arg)
                            for arg in _typing.get_args(annotation)
                        )
                except Exception:
                    pass
                try:
                    return "fastmcp" in str(annotation)
                except Exception:
                    return False

            try:
                sig = sig if "sig" in locals() else _inspect.signature(fn)
                for p in sig.parameters.values():
                    needs_fast_ctx = False
                    if _is_fast_ctx_annotation(p.annotation):
                        needs_fast_ctx = True
                    elif p.annotation is _inspect._empty and p.name in (
                        "ctx",
                        "context",
                    ):
                        needs_fast_ctx = True
                    if needs_fast_ctx and p.name not in call_kwargs:
                        fast_ctx = getattr(workflow_self, "_mcp_request_context", None)
                        if fast_ctx is None and app_context_param_name:
                            _app_ctx = call_kwargs.get(app_context_param_name, None)
                            if _Ctx is not None and isinstance(_app_ctx, _Ctx):
                                fast_ctx = _app_ctx
                            _fastmcp = getattr(_app_ctx, "fastmcp", None)
                            if _fastmcp is not None and hasattr(
                                _fastmcp, "get_context"
                            ):
                                try:
                                    fast_ctx = _fastmcp.get_context()
                                except Exception:
                                    fast_ctx = None
                        if fast_ctx is not None:
                            call_kwargs[p.name] = fast_ctx
            except Exception:
                pass

            # If user passed a single positional dict (Temporal AutoWorkflow payload), merge it
            if not call_kwargs and len(args) == 1 and isinstance(args[0], dict):
                call_kwargs = dict(args[0])
                args = ()

            # Support both async and sync callables
            res = fn(*args, **call_kwargs)
            if _asyncio.iscoroutine(res):
                res = await res

            # Ensure WorkflowResult return type
            try:
                from mcp_agent.executor.workflow import (
                    WorkflowResult as _WorkflowResult,
                )
            except Exception:
                _WorkflowResult = None  # type: ignore[assignment]

            if _WorkflowResult is not None and not isinstance(res, _WorkflowResult):
                return _WorkflowResult(value=res)
            return res

        async def _run(self, *args, **kwargs):  # type: ignore[no-redef]
            # ensure initialization
            await self.initialize()
            return await _invoke_target(self, *args, **kwargs)

        # Decorate run with engine-specific decorator
        engine_type = self.config.execution_engine
        if engine_type == "temporal":
            # Temporal requires the @workflow.run to be applied on a top-level
            # class method, not on a local function. We'll assign _run as-is
            # for now and decorate it after creating and publishing the class.
            decorated_run = _run
        else:
            decorated_run = self.workflow_run(_run)

        # Build the Workflow subclass dynamically
        cls_dict: Dict[str, Any] = {
            "__doc__": description or (fn.__doc__ or ""),
            "run": decorated_run,
            "__mcp_agent_param_source_fn__": fn,
        }
        if mark_sync_tool:
            cls_dict["__mcp_agent_sync_tool__"] = True
        else:
            cls_dict["__mcp_agent_async_tool__"] = True

        auto_cls = type(f"AutoWorkflow_{workflow_name}", (_Workflow,), cls_dict)

        # Workaround for Temporal: publish the dynamically created class as a
        # top-level (module global) so it is not considered a "local class".
        # Temporal requires workflow classes to be importable from a module.
        try:
            import sys as _sys

            target_module = getattr(fn, "__module__", __name__)
            auto_cls.__module__ = target_module
            _mod = _sys.modules.get(target_module)
            if _mod is not None:
                setattr(_mod, auto_cls.__name__, auto_cls)
        except Exception:
            pass

        # For Temporal, now that the class exists and is published at module-level,
        # decorate the run method with the engine-specific run decorator.
        if engine_type == "temporal":
            try:
                run_decorator = self._decorator_registry.get_workflow_run_decorator(
                    engine_type
                )
                if run_decorator:
                    fn_run = getattr(auto_cls, "run")
                    # Ensure method appears as top-level for Temporal
                    target_module = getattr(fn, "__module__", __name__)
                    try:
                        fn_run.__module__ = target_module  # type: ignore[attr-defined]
                        fn_run.__qualname__ = f"{auto_cls.__name__}.run"  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    setattr(auto_cls, "run", run_decorator(fn_run))
            except Exception:
                pass

        # Register with app (and apply engine-specific workflow decorator)
        self.workflow(auto_cls, workflow_id=workflow_name)
        return auto_cls

    @overload
    def tool(self, __fn: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def tool(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | Mapping[str, Any] | None = None,
        icons: Iterable[Icon | Mapping[str, Any]] | None = None,
        meta: Mapping[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def tool(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | Mapping[str, Any] | None = None,
        icons: Iterable[Icon | Mapping[str, Any]] | None = None,
        meta: Mapping[str, Any] | None = None,
        structured_output: bool | None = None,
    ):
        """
        Decorator to declare a synchronous MCP tool that runs via an auto-generated
        Workflow and waits for completion before returning.

        Also registers an async Workflow under the same name so that run/get_status
        endpoints are available.
        """

        def decorator(fn: Callable[P, R]) -> Callable[P, R]:
            tool_name = name or fn.__name__

            # Early validation: Use the shared tool adapter logic to validate
            # that the transformed function can be converted to JSON schema

            validate_tool_schema(fn, tool_name)

            annotations_obj: ToolAnnotations | None = None
            if annotations is not None:
                if isinstance(annotations, ToolAnnotations):
                    annotations_obj = annotations
                else:
                    annotations_obj = ToolAnnotations(**dict(annotations))

            icons_list: list[Icon] | None = None
            if icons is not None:
                icons_list = []
                for icon in icons:
                    if isinstance(icon, Icon):
                        icons_list.append(icon)
                    elif isinstance(icon, Mapping):
                        icons_list.append(Icon(**icon))
                    else:
                        raise TypeError("icons entries must be Icon or mapping")
            else:
                icons_list = [phetch]

            meta_payload: Dict[str, Any] | None = None
            if meta is not None:
                meta_payload = dict(meta)

            # Construct the workflow from function
            workflow_cls = self._create_workflow_from_function(
                fn,
                workflow_name=tool_name,
                description=description,
                mark_sync_tool=True,
            )

            # Defer tool registration until the MCP server is created
            self._declared_tools.append(
                {
                    "name": tool_name,
                    "mode": "sync",
                    "workflow_name": tool_name,
                    "workflow_cls": workflow_cls,
                    "source_fn": fn,
                    "structured_output": structured_output,
                    "description": description or (fn.__doc__ or ""),
                    "title": title,
                    "annotations": annotations_obj,
                    "icons": icons_list,
                    "meta": meta_payload,
                }
            )

            return fn

        # Support bare usage: @app.tool without parentheses
        if (
            callable(name)
            and title is None
            and description is None
            and annotations is None
            and icons is None
            and meta is None
            and structured_output is None
        ):
            _fn = name  # type: ignore[assignment]
            name = None
            return decorator(_fn)  # type: ignore[arg-type]

        return decorator

    def _normalize_workflow_retry_policy(
        self, retry_policy: WorkflowTaskRetryPolicy | Dict[str, Any] | None
    ) -> WorkflowTaskRetryPolicy | None:
        """Normalize workflow retry policies defined via decorator arguments."""
        if retry_policy is None:
            return None
        if isinstance(retry_policy, WorkflowTaskRetryPolicy):
            return retry_policy
        if isinstance(retry_policy, dict):
            return WorkflowTaskRetryPolicy(**retry_policy)
        raise TypeError("workflow retry policy must be WorkflowTaskRetryPolicy or dict")

    @overload
    def async_tool(self, __fn: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def async_tool(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | Mapping[str, Any] | None = None,
        icons: Iterable[Icon | Mapping[str, Any]] | None = None,
        meta: Mapping[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def async_tool(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | Mapping[str, Any] | None = None,
        icons: Iterable[Icon | Mapping[str, Any]] | None = None,
        meta: Mapping[str, Any] | None = None,
        structured_output: bool | None = None,
    ):
        """
        Decorator to declare an asynchronous MCP tool.

        Creates a Workflow class from the function and registers it so that
        the standard per-workflow tools (run/get_status) are exposed by the server.
        """

        def decorator(fn: Callable[P, R]) -> Callable[P, R]:
            workflow_name = name or fn.__name__

            # Early validation: Use the shared tool adapter logic to validate
            # that the transformed function can be converted to JSON schema
            from mcp_agent.server.tool_adapter import validate_tool_schema

            validate_tool_schema(fn, workflow_name)

            annotations_obj: ToolAnnotations | None = None
            if annotations is not None:
                if isinstance(annotations, ToolAnnotations):
                    annotations_obj = annotations
                else:
                    annotations_obj = ToolAnnotations(**dict(annotations))

            icons_list: list[Icon] | None = None
            if icons is not None:
                icons_list = []
                for icon in icons:
                    if isinstance(icon, Icon):
                        icons_list.append(icon)
                    elif isinstance(icon, Mapping):
                        icons_list.append(Icon(**icon))
                    else:
                        raise TypeError("icons entries must be Icon or mapping")
            else:
                icons_list = [phetch]

            meta_payload: Dict[str, Any] | None = None
            if meta is not None:
                meta_payload = dict(meta)

            workflow_cls = self._create_workflow_from_function(
                fn,
                workflow_name=workflow_name,
                description=description,
                mark_sync_tool=False,
            )

            # Defer alias tool registration for run/get_status
            self._declared_tools.append(
                {
                    "name": workflow_name,
                    "mode": "async",
                    "workflow_name": workflow_name,
                    "workflow_cls": workflow_cls,
                    "source_fn": fn,
                    "structured_output": structured_output,
                    "description": description or (fn.__doc__ or ""),
                    "title": title,
                    "annotations": annotations_obj,
                    "icons": icons_list,
                    "meta": meta_payload,
                }
            )
            return fn

        # Support bare usage: @app.async_tool without parentheses
        if (
            callable(name)
            and title is None
            and description is None
            and annotations is None
            and icons is None
            and meta is None
            and structured_output is None
        ):
            _fn = name  # type: ignore[assignment]
            name = None
            return decorator(_fn)  # type: ignore[arg-type]

        return decorator

    def _get_configured_retry_policy(self, activity_name: str) -> Dict[str, Any] | None:
        """
        Compute the retry policy override for a workflow task.

        Matching precedence (highest first):
        - Exact full activity name (e.g., ``package.module.task``)
        - Dotted suffix match (``task`` or ``module.task``)
        - Prefix wildcard (``package.*``), with longest prefix winning
        - Global fallback (``*``)
        """
        overrides = getattr(self.config, "workflow_task_retry_policies", None)
        if not overrides:
            return None

        def coerce(policy: Any) -> Dict[str, Any]:
            if policy is None:
                return {}
            if hasattr(policy, "to_temporal_kwargs"):
                return policy.to_temporal_kwargs()
            return dict(policy)

        best_match: tuple[int, int, Dict[str, Any]] | None = None

        def record(priority: int, length: int, policy_dict: Dict[str, Any]):
            nonlocal best_match
            candidate = (priority, length, policy_dict)
            if best_match is None or candidate > best_match:
                best_match = candidate

        for key, policy_obj in overrides.items():
            policy_dict = coerce(policy_obj)
            if not policy_dict:
                continue

            if key == "*":
                record(0, 0, policy_dict)
                continue

            if key.endswith("*"):
                prefix = key[:-1]
                if activity_name.startswith(prefix):
                    record(1, len(prefix), policy_dict)
                continue

            if "." in key:
                if activity_name == key:
                    record(3, len(key), policy_dict)
                elif activity_name.endswith(f".{key}"):
                    record(2, len(key), policy_dict)
                continue

            if activity_name.split(".")[-1] == key:
                record(2, len(key), policy_dict)

        return best_match[2] if best_match else None

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

            override_policy = self._get_configured_retry_policy(activity_name)
            if override_policy:
                existing_policy = metadata.get("retry_policy") or {}
                metadata["retry_policy"] = {**existing_policy, **override_policy}

            # bookkeeping that survives partial/bound wrappers
            func.is_workflow_task = True
            func.execution_metadata = metadata

            task_defn = self._decorator_registry.get_workflow_task_decorator(
                self.config.execution_engine
            )

            if task_defn:
                # Prevent re-decoration of an already temporal-decorated function,
                # but still register it with the app.
                if hasattr(target, "__temporal_activity_definition"):
                    self.logger.debug(
                        "Skipping redecorate for already-temporal activity",
                        data={"activity_name": activity_name},
                    )
                    task_callable = target
                elif isinstance(target, MethodType):
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

            override_policy = self._get_configured_retry_policy(activity_name)
            if override_policy:
                existing_policy = metadata.get("retry_policy") or {}
                metadata["retry_policy"] = {**existing_policy, **override_policy}

            func.is_workflow_task = True
            func.execution_metadata = metadata

            # Apply the engine-specific decorator if available
            task_defn = self._decorator_registry.get_workflow_task_decorator(
                self.config.execution_engine
            )

            if task_defn:  # Engine-specific decorator available
                # Prevent re-decoration of an already temporal-decorated function,
                # but still register it with the app.
                if hasattr(target, "__temporal_activity_definition"):
                    self.logger.debug(
                        "Skipping redecorate for already-temporal activity",
                        data={"activity_name": activity_name},
                    )
                    task_callable = target
                elif isinstance(target, MethodType):
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
