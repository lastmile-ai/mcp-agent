"""
MCP Agent Temporal Plugin

This plugin provides MCP Agent functionality as a Temporal plugin, allowing users to add
MCP Agent capabilities to their Temporal workflows with a single line of configuration.
"""

from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator, Dict, Any, Optional, TYPE_CHECKING
import warnings

from temporalio.worker import (
    Plugin as WorkerPlugin,
    Replayer,
    ReplayerConfig,
    Worker,
    WorkerConfig,
    WorkflowReplayResult,
)
from temporalio.client import ClientConfig, Plugin as ClientPlugin, WorkflowHistory
from temporalio.contrib.pydantic import (
    PydanticPayloadConverter,
    pydantic_data_converter,
)
from temporalio.converter import DataConverter, DefaultPayloadConverter
from temporalio.service import ConnectConfig, ServiceClient
from temporalio.contrib.opentelemetry import TracingInterceptor

from mcp_agent.executor.temporal.interceptor import ContextPropagationInterceptor
from mcp_agent.config import TemporalSettings
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.core.context import Context
    from mcp_agent.app import MCPApp

logger = get_logger(__name__)


class MCPAgentPlugin(ClientPlugin, WorkerPlugin):
    """
    Temporal plugin for MCP Agent functionality.

    This plugin provides:
    - Built-in MCP activities (tool calling, logging, human input)
    - Pydantic data converter for seamless serialization
    - Context propagation interceptors
    - Tracing support
    - Auto-registration of workflow tasks as activities

    Usage with config file:
        from mcp_agent.config import Settings

        settings = Settings.from_file("mcp_agent.config.yaml")
        plugin = MCPAgentPlugin(config=settings.temporal)

        client = await Client.connect("localhost:7233", plugins=[plugin])
        worker = Worker(client, task_queue="my-queue", workflows=[MyWorkflow], plugins=[plugin])

    Usage with direct configuration:
        plugin = MCPAgentPlugin(
            host="localhost:7233",
            namespace="default",
            task_queue="mcp-agent",
            max_concurrent_activities=10
        )
    """

    def __init__(
        self,
        config: Optional[TemporalSettings] = None,
        context: Optional["Context"] = None,
        app: Optional["MCPApp"] = None,
        **kwargs
    ):
        """
        Initialize the MCP Agent Temporal plugin.

        Args:
            config: Temporal configuration settings (from config file or TemporalSettings object)
            context: MCP Agent context (optional, will be created if not provided)
            app: MCP App instance (optional, for workflow registration)
            **kwargs: Additional configuration passed to TemporalSettings if config not provided
                     Supported kwargs:
                     - host: Temporal server address (e.g., "localhost:7233")
                     - namespace: Temporal namespace (default: "default")
                     - task_queue: Task queue name (default: "mcp-agent")
                     - api_key: API key for Temporal Cloud
                     - tls: TLS configuration
                     - max_concurrent_activities: Maximum concurrent activities
                     - timeout_seconds: Default activity timeout
                     - rpc_metadata: Additional RPC metadata dict
                     - id_reuse_policy: Workflow ID reuse policy
        """
        # Use provided config or create from kwargs
        self.config = config or TemporalSettings(**kwargs)
        self.context = context
        self.app = app
        self._system_activities = None
        self._agent_tasks = None

    def init_client_plugin(self, next: ClientPlugin) -> None:
        self.next_client_plugin = next

    def init_worker_plugin(self, next: WorkerPlugin) -> None:
        self.next_worker_plugin = next

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        """Configure the Temporal client with MCP Agent settings."""
        # Set up data converter
        config["data_converter"] = self._get_new_data_converter(
            config.get("data_converter")
        )

        # Add interceptors
        interceptors = list(config.get("interceptors") or [])

        # Add tracing if enabled
        if self.context and getattr(self.context, 'tracing_enabled', False):
            interceptors.append(TracingInterceptor())

        # Always add context propagation
        interceptors.append(ContextPropagationInterceptor())

        config["interceptors"] = interceptors

        # Set namespace from config if available
        if self.config and self.config.namespace:
            config["namespace"] = self.config.namespace

        return self.next_client_plugin.configure_client(config)

    async def connect_service_client(self, config: ConnectConfig) -> ServiceClient:
        """Configure service connection with MCP Agent settings from config."""
        # Apply connection settings from TemporalSettings config
        if self.config:
            if self.config.host:
                config.target_host = self.config.host
            if self.config.namespace:
                config.namespace = self.config.namespace
            if self.config.api_key:
                config.api_key = self.config.api_key
            if self.config.tls is not None:
                config.tls = self.config.tls
            if self.config.rpc_metadata:
                # Merge existing metadata with config metadata
                existing_metadata = getattr(config, 'rpc_metadata', {}) or {}
                config.rpc_metadata = {**existing_metadata, **self.config.rpc_metadata}

        return await self.next_client_plugin.connect_service_client(config)

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure the worker with MCP Agent activities and settings."""
        activities = list(config.get("activities") or [])

        # Initialize system activities if we have context
        if self.context:
            # Register system activities (already decorated with @activity.defn)
            if not self._system_activities:
                from mcp_agent.executor.temporal.system_activities import SystemActivities
                self._system_activities = SystemActivities(context=self.context)

            # Add system activities - they're already decorated, just add them directly
            activities.extend(
                [
                    self._system_activities.forward_log,
                    self._system_activities.request_user_input,
                    self._system_activities.relay_notify,
                    self._system_activities.relay_request,
                ]
            )

            # Register agent tasks if available
            if not self._agent_tasks:
                from mcp_agent.agents.agent import AgentTasks
                self._agent_tasks = AgentTasks(context=self.context)

            # Register agent tasks - create wrapper functions for bound methods
            # since we're in a plugin context, not relying on the app's executor
            from temporalio import activity
            import functools

            # Create wrapper functions for agent tasks (bound methods can't be decorated directly)
            def make_activity_wrapper(method, name):
                @functools.wraps(method)
                async def wrapper(*args, **kwargs):
                    return await method(*args, **kwargs)
                return activity.defn(name=name)(wrapper)

            activities.extend([
                make_activity_wrapper(self._agent_tasks.call_tool_task, "mcp_agent.call_tool_task"),
                make_activity_wrapper(self._agent_tasks.get_capabilities_task, "mcp_agent.get_capabilities_task"),
                make_activity_wrapper(self._agent_tasks.get_prompt_task, "mcp_agent.get_prompt_task"),
                make_activity_wrapper(self._agent_tasks.initialize_aggregator_task, "mcp_agent.initialize_aggregator_task"),
                make_activity_wrapper(self._agent_tasks.list_prompts_task, "mcp_agent.list_prompts_task"),
                make_activity_wrapper(self._agent_tasks.list_tools_task, "mcp_agent.list_tools_task"),
                make_activity_wrapper(self._agent_tasks.shutdown_aggregator_task, "mcp_agent.shutdown_aggregator_task"),
            ])

            # Auto-discover and register activities from task registry
            # When using asyncio executor, activities won't be decorated with @activity.defn
            # So we need to wrap them here for Temporal use
            if hasattr(self.context, 'task_registry'):
                activity_registry = self.context.task_registry

                for name in activity_registry.list_activities():
                    activity_func = activity_registry.get_activity(name)

                    # Check if already a Temporal activity
                    if hasattr(activity_func, "__temporal_activity_definition"):
                        activities.append(activity_func)
                    else:
                        # Create wrapper for non-Temporal activities (handles both functions and bound methods)
                        try:
                            # Use the same wrapper pattern as agent tasks
                            wrapped = make_activity_wrapper(activity_func, name)
                            activities.append(wrapped)
                        except Exception as e:
                            # Skip if there are issues
                            logger.debug(f"Skipping activity {name}: {e}")

        config["activities"] = activities

        # Add interceptors
        config["interceptors"] = list(config.get("interceptors") or []) + [
            ContextPropagationInterceptor()
        ]

        # Set task queue from config if available
        if self.config and self.config.task_queue:
            config["task_queue"] = self.config.task_queue

        # Add workflows from app if available
        if self.app and hasattr(self.app, 'workflows'):
            existing_workflows = list(config.get("workflows") or [])
            existing_workflows.extend(self.app.workflows.values())
            config["workflows"] = existing_workflows

        # Configure workflow sandbox to allow MCP Agent modules
        from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
        from dataclasses import replace

        runner = config.get('workflow_runner')
        if isinstance(runner, SandboxedWorkflowRunner):
            # Disable most restrictions for MCP Agent workflows
            # This is necessary because MCP Agent code uses many libraries that aren't workflow-safe by default
            config['workflow_runner'] = replace(
                runner,
                restrictions=runner.restrictions.with_passthrough_modules(
                    # MCP Agent modules - pass through everything
                    'mcp_agent',
                    'mcp',
                    # AI/ML libraries
                    'openai',
                    'anthropic',
                    'google',
                    'pydantic',
                    'pydantic_core',
                    'pydantic_ai',
                    # Logging and tracing
                    'logfire',
                    'rich',
                    'logging',
                    'opentelemetry',
                    # HTTP clients and networking
                    'httpx',
                    'httpcore',
                    'aiohttp',
                    'urllib3',
                    'requests',
                    # Async libraries
                    'asyncio',
                    'anyio',
                    'sniffio',
                    # Data processing
                    'attrs',
                    'numpy',
                    'pandas',
                    # Threading and concurrency (needed by many libraries)
                    'threading',
                    'concurrent',
                    'multiprocessing',
                    # Standard library modules
                    'datetime',
                    'json',
                    'typing',
                    'typing_extensions',
                    'dataclasses',
                    'functools',
                    'collections',
                    're',
                    'uuid',
                    'hashlib',
                    'base64',
                    'os',
                    'sys',
                    'pathlib',
                    'warnings',
                ),
            )

        return self.next_worker_plugin.configure_worker(config)

    async def run_worker(self, worker: Worker) -> None:
        """Run the worker with MCP Agent context."""
        # Set up any necessary context before running the worker
        await self.next_worker_plugin.run_worker(worker)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        """Configure the replayer with MCP Agent settings."""
        config["data_converter"] = self._get_new_data_converter(
            config.get("data_converter")
        )
        return self.next_worker_plugin.configure_replayer(config)

    def run_replayer(
        self,
        replayer: Replayer,
        histories: AsyncIterator[WorkflowHistory],
    ) -> AbstractAsyncContextManager[AsyncIterator[WorkflowReplayResult]]:
        """Run the replayer with MCP Agent context."""
        return self.next_worker_plugin.run_replayer(replayer, histories)

    def _get_new_data_converter(self, converter: DataConverter | None) -> DataConverter:
        """Get or create a Pydantic data converter, warning if replacing a custom one."""
        if converter and converter.payload_converter_class not in (
            DefaultPayloadConverter,
            PydanticPayloadConverter,
        ):
            warnings.warn(
                "A non-default Temporal data converter was provided but has been replaced "
                "with the Pydantic data converter for MCP Agent compatibility."
            )

        return pydantic_data_converter
