"""
MCP Agent Temporal Plugin

This plugin provides MCP Agent functionality as a Temporal plugin, allowing users to add
MCP Agent capabilities to their Temporal workflows with a single line of configuration.
"""

from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator, TYPE_CHECKING
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
from mcp_agent.executor.temporal.session_proxy import SessionProxy
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.app import MCPApp

logger = get_logger(__name__)


class MCPAgentPlugin(ClientPlugin, WorkerPlugin):
    """
    Temporal plugin for integrating MCP Agent with Temporal workflows.

    This plugin provides seamless integration between the MCP Agent SDK and
    Temporal workflows. It automatically configures the necessary interceptors,
    activities, and data converters to enable MCP Agent to run within
    Temporal workflows with proper tracing and model execution.

    This plugin provides:
    - Built-in MCP Agent activities
    - Pydantic data converter for seamless serialization
    - Context propagation interceptors
    - Tracing support
    - Auto-registration of workflow tasks as activities

    Example:
    ```
        app = MCPApp(name="mcp_basic_agent")
        async with app.run() as running_app:
            plugin = MCPAgentPlugin(app)
            client = await Client.connect("localhost:7233", plugins=[plugin])
            worker = Worker(client, task_queue="my-queue", workflows=[MyWorkflow])
    ```
    """

    def __init__(self, app: "MCPApp"):
        """Initialize MCP Agent Temporal plugin.

        Args:
            app (MCPApp): MCP Agent app instance
        """
        self.app = app
        self.temporal_config = self.app.config.temporal
        self.context = self.app.context
        self._system_activities = None
        self._agent_tasks = None

        # Expose a virtual upstream session (passthrough) bound to this run via activities
        # This lets any code use context.upstream_session like a real session.
        upstream_session = getattr(self.context, "upstream_session", None)
        if upstream_session is None:
            self.context.upstream_session = SessionProxy(
                executor=self.context.executor,
                context=self.context,
            )
            app = self.context.app
            if app:
                # Ensure the app's logger is bound to the current context with upstream_session
                if app._logger and hasattr(app._logger, "_bound_context"):
                    app._logger._bound_context = self.context

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
        if self.context and getattr(self.context, "tracing_enabled", False):
            interceptors.append(TracingInterceptor())

        # Always add context propagation
        interceptors.append(ContextPropagationInterceptor())

        config["interceptors"] = interceptors

        # Set namespace from config if available
        if self.temporal_config and self.temporal_config.namespace:
            config["namespace"] = self.temporal_config.namespace

        return self.next_client_plugin.configure_client(config)

    async def connect_service_client(self, config: ConnectConfig) -> ServiceClient:
        """Configure service connection with MCP Agent settings from config."""
        # Apply connection settings from TemporalSettings config
        if self.temporal_config:
            if self.temporal_config.host:
                config.target_host = self.temporal_config.host
            if self.temporal_config.namespace:
                config.namespace = self.temporal_config.namespace
            if self.temporal_config.api_key:
                config.api_key = self.temporal_config.api_key
            if self.temporal_config.tls is not None:
                config.tls = self.temporal_config.tls
            if self.temporal_config.rpc_metadata:
                # Merge existing metadata with config metadata
                existing_metadata = getattr(config, "rpc_metadata", {}) or {}
                config.rpc_metadata = {
                    **existing_metadata,
                    **self.temporal_config.rpc_metadata,
                }

        return await self.next_client_plugin.connect_service_client(config)

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure the worker with MCP Agent activities and settings."""
        activities = list(config.get("activities") or [])

        # Initialize and register activities if we have context and app
        if self.context and self.app:
            # Register agent tasks using app.workflow_task()
            if not self._agent_tasks:
                from mcp_agent.agents.agent import AgentTasks

                self._agent_tasks = AgentTasks(context=self.context)

            self.app.workflow_task()(self._agent_tasks.call_tool_task)
            self.app.workflow_task()(self._agent_tasks.get_capabilities_task)
            self.app.workflow_task()(self._agent_tasks.get_prompt_task)
            self.app.workflow_task()(self._agent_tasks.initialize_aggregator_task)
            self.app.workflow_task()(self._agent_tasks.list_prompts_task)
            self.app.workflow_task()(self._agent_tasks.list_tools_task)
            self.app.workflow_task()(self._agent_tasks.shutdown_aggregator_task)

            # Register system activities using app.workflow_task()
            if not self._system_activities:
                from mcp_agent.executor.temporal.system_activities import (
                    SystemActivities,
                )

                self._system_activities = SystemActivities(context=self.context)

            self.app.workflow_task(name="mcp_forward_log")(
                self._system_activities.forward_log
            )
            self.app.workflow_task(name="mcp_request_user_input")(
                self._system_activities.request_user_input
            )
            self.app.workflow_task(name="mcp_relay_notify")(
                self._system_activities.relay_notify
            )
            self.app.workflow_task(name="mcp_relay_request")(
                self._system_activities.relay_request
            )

            # Collect activities from the task registry
            if hasattr(self.context, "task_registry"):
                activity_registry = self.context.task_registry
                for name in activity_registry.list_activities():
                    activities.append(activity_registry.get_activity(name))

        else:
            warnings.warn("No context and app - Activities not registered.")

        config["activities"] = activities

        # Add interceptors
        config["interceptors"] = list(config.get("interceptors") or []) + [
            ContextPropagationInterceptor()
        ]

        # Set task queue from config if available
        if self.temporal_config and self.temporal_config.task_queue:
            config["task_queue"] = self.temporal_config.task_queue

        # Add workflows from app if available
        if self.app and hasattr(self.app, "workflows"):
            existing_workflows = list(config.get("workflows") or [])
            existing_workflows.extend(self.app.workflows.values())
            config["workflows"] = existing_workflows

        # Configure workflow sandbox to allow MCP Agent modules
        from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
        from dataclasses import replace

        runner = config.get("workflow_runner")
        if isinstance(runner, SandboxedWorkflowRunner):
            # Disable most restrictions for MCP Agent workflows
            # This is necessary because MCP Agent code uses many libraries that aren't workflow-safe by default
            config["workflow_runner"] = replace(
                runner,
                restrictions=runner.restrictions.with_passthrough_modules(
                    "mcp_agent",
                    "mcp",
                    "rich",
                    "logging",
                    "opentelemetry",
                    "httpx",
                    "httpcore",
                    "sniffio",
                    "aiohttp",
                    "attrs",
                    "numpy",
                    "pydantic",
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
