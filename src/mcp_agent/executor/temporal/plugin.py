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

        # Register activities with the app so they're available in workflow context
        self._register_activities()

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

    def _register_activities(self) -> None:
        """Register MCP Agent activities."""
        if not (self.context and self.app):
            warnings.warn("No context and app - Activities not registered.")
            return

        # Register agent tasks
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

        # Register system activities
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

    def _configure_activities(self, config: dict) -> None:
        """Add registered activities to Worker config.

        This method modifies the config dict in place by adding activities
        to config["activities"].
        """
        activities = list(config.get("activities") or [])

        if self.context and hasattr(self.context, "task_registry"):
            # Collect activities from the task registry
            activity_registry = self.context.task_registry
            for name in activity_registry.list_activities():
                activities.append(activity_registry.get_activity(name))

        config["activities"] = activities

    def _configure_workflows(self, config: dict) -> None:
        """Add workflows from app to configuration.

        This method modifies the config dict in place.
        """
        if self.app and hasattr(self.app, "workflows"):
            existing_workflows = list(config.get("workflows") or [])

            # Register Temporal workflows passed to Worker
            if existing_workflows:
                unregistered_workflows = []
                for workflow_cls in existing_workflows:
                    # Check if this is a Temporal workflow
                    if hasattr(workflow_cls, "__temporal_workflow_definition"):
                        workflow_id = workflow_cls.__name__
                        # If not registered with MCPApp, add it to the list
                        if workflow_id not in self.app.workflows:
                            unregistered_workflows.append(workflow_cls)

                # Register all unregistered workflows with MCPApp
                if unregistered_workflows:
                    self.app._register_temporal_workflows(unregistered_workflows)

            app_workflows = list(self.app.workflows.values())

            # Deduplicate workflows by class - avoid registering the same workflow class twice
            all_workflows = existing_workflows + app_workflows
            unique_workflows = []
            seen_classes = set()

            for workflow_cls in all_workflows:
                if workflow_cls not in seen_classes:
                    unique_workflows.append(workflow_cls)
                    seen_classes.add(workflow_cls)

            config["workflows"] = unique_workflows

    def _configure_workflow_runner(self, config: dict) -> None:
        """Configure workflow sandbox runner with MCP Agent modules.

        This method modifies the config dict in place.
        """
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

    def _configure_interceptors(self, config: dict) -> None:
        """Configure interceptors for tracing and context propagation.

        This method modifies the config dict in place.
        """
        interceptors = list(config.get("interceptors") or [])

        # Add tracing if enabled
        if self.context and getattr(self.context, "tracing_enabled", False):
            interceptors.append(TracingInterceptor())

        # Always add context propagation
        interceptors.append(ContextPropagationInterceptor())

        config["interceptors"] = interceptors

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        """Configure the worker with MCP Agent activities and settings."""
        self._configure_activities(config)

        self._configure_workflows(config)

        self._configure_workflow_runner(config)

        self._configure_interceptors(config)

        # Set task queue from config if available (Worker-specific)
        if self.temporal_config and self.temporal_config.task_queue:
            config["task_queue"] = self.temporal_config.task_queue

        return self.next_worker_plugin.configure_worker(config)

    async def run_worker(self, worker: Worker) -> None:
        """Run the worker with MCP Agent context."""
        # Set up any necessary context before running the worker
        await self.next_worker_plugin.run_worker(worker)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        """Configure the replayer with MCP Agent settings."""
        # Configure data converter
        config["data_converter"] = self._get_new_data_converter(
            config.get("data_converter")
        )

        self._configure_workflows(config)

        self._configure_workflow_runner(config)

        self._configure_interceptors(config)

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
