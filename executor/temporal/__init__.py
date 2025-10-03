"""
Temporal based orchestrator for the MCP Agent.
Temporal provides durable execution and robust workflow orchestration,
as well as dynamic control flow, making it a good choice for an AI agent orchestrator.
Read more: https://docs.temporal.io/develop/python/core-application
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import functools
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)
import inspect

from mcp_agent.human_input.types import HumanInputRequest
from pydantic import ConfigDict
from temporalio import activity, workflow, exceptions
from temporalio.client import Client as TemporalClient, WorkflowHandle
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.common import WorkflowIDReusePolicy
from temporalio.worker import Worker

from mcp_agent.config import TemporalSettings
from mcp_agent.executor.executor import Executor, ExecutorConfig, R

from mcp_agent.executor.temporal.workflow_signal import TemporalSignalHandler
from mcp_agent.executor.workflow_signal import SignalHandler
from mcp_agent.logging.logger import get_logger
from mcp_agent.utils.common import unwrap
from mcp_agent.executor.temporal.interceptor import ContextPropagationInterceptor
from mcp_agent.executor.temporal.system_activities import SystemActivities

if TYPE_CHECKING:
    from mcp_agent.app import MCPApp
    from mcp_agent.core.context import Context
    from random import Random
    from uuid import UUID

logger = get_logger(__name__)


class TemporalExecutorConfig(ExecutorConfig, TemporalSettings):
    """Configuration for Temporal executors."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TemporalExecutor(Executor):
    """Executor that runs @workflows as Temporal workflows, with @workflow_tasks as Temporal activities"""

    def __init__(
        self,
        config: TemporalExecutorConfig | None = None,
        signal_bus: SignalHandler | None = None,
        client: TemporalClient | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        signal_bus = signal_bus or TemporalSignalHandler(executor=self)
        super().__init__(
            engine="temporal",
            config=config,
            signal_bus=signal_bus,
            context=context,
            **kwargs,
        )
        self.config: TemporalExecutorConfig = (
            config or self.context.config.temporal or TemporalExecutorConfig()
        )
        self.client = client
        self._worker = None
        self._activity_semaphore = None

        if config.max_concurrent_activities is not None:
            self._activity_semaphore = asyncio.Semaphore(
                self.config.max_concurrent_activities
            )

    @staticmethod
    def wrap_as_activity(
        activity_name: str,
        func: Callable[..., R] | Coroutine[Any, Any, R],
        **kwargs: Any,
    ) -> Coroutine[Any, Any, R]:
        """
        Convert a function into a Temporal activity and return its info.
        """

        @activity.defn(name=activity_name)
        async def wrapped_activity(*args, **local_kwargs):
            """
            Temporal activity wrapper that supports both payload styles:
            - Single dict payload: wrapped_activity({"k": v, ...}) -> func(**payload)
            - Varargs/kwargs payload: wrapped_activity(a, b, c, x=1) -> func(a, b, c, x=1)
            """
            try:
                # Prefer the legacy single-dict payload convention when applicable
                if len(args) == 1 and isinstance(args[0], dict) and not local_kwargs:
                    payload = args[0]
                    if asyncio.iscoroutinefunction(func):
                        return await func(**payload)
                    elif asyncio.iscoroutine(func):
                        return await func
                    else:
                        return func(**payload)
                else:
                    # Fall back to passing through varargs/kwargs directly
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **local_kwargs)
                    elif asyncio.iscoroutine(func):
                        return await func
                    else:
                        return func(*args, **local_kwargs)
            except Exception as e:
                # Properly surface activity exceptions
                raise e

        return wrapped_activity

    async def _execute_task_as_async(
        self, task: Callable[..., R] | Coroutine[Any, Any, R], *args, **kwargs
    ) -> R | BaseException:
        async def run_task(task: Callable[..., R] | Coroutine[Any, Any, R]) -> R:
            try:
                if asyncio.iscoroutine(task):
                    return await task
                elif asyncio.iscoroutinefunction(task):
                    return await task(*args, **kwargs)
                else:
                    # Check if we're in a Temporal workflow context
                    if workflow.in_workflow():
                        wrapped_task = functools.partial(task, *args, **kwargs)
                        result = wrapped_task()
                    else:
                        # Outside a workflow, use standard asyncio executor
                        loop = asyncio.get_running_loop()
                        wrapped_task = functools.partial(task, *args, **kwargs)
                        result = await loop.run_in_executor(None, wrapped_task)

                    # Handle case where the sync function returns a coroutine
                    if asyncio.iscoroutine(result):
                        return await result

                    return result
            except Exception as e:
                # TODO: saqadri - set up logger
                # logger.error(f"Error executing task: {e}")
                return e

        if self._activity_semaphore:
            async with self._activity_semaphore:
                return await run_task(task)
        else:
            return await run_task(task)

    async def _execute_task(
        self, task: Callable[..., R] | Coroutine[Any, Any, R], *args, **kwargs
    ) -> R | BaseException:
        func = task.func if isinstance(task, functools.partial) else task
        func = unwrap(func)

        is_workflow_task = getattr(func, "is_workflow_task", False)
        execution_metadata: Dict[str, Any] = getattr(func, "execution_metadata", {})
        activity_name: str | None = execution_metadata.get("activity_name", None)

        if not is_workflow_task or not activity_name:
            return await self._execute_task_as_async(task, *args, **kwargs)

        activity_registry = self.context.task_registry
        activity_task = activity_registry.get_activity(activity_name)

        # Config timeout takes priority over metadata timeout (per tests).
        schedule_to_close = self.config.timeout_seconds or execution_metadata.get(
            "schedule_to_close_timeout"
        )

        if schedule_to_close is not None and not isinstance(
            schedule_to_close, timedelta
        ):
            # Convert numeric seconds to timedelta if needed
            schedule_to_close = timedelta(seconds=schedule_to_close)

        retry_policy = execution_metadata.get("retry_policy", None)

        try:
            # Temporal's execute_activity accepts at most one positional arg;
            # pass user args via the keyword-only 'args' to support multiple
            result = await workflow.execute_activity(
                activity_task,
                args=list(args) if args else None,
                task_queue=self.config.task_queue,
                schedule_to_close_timeout=schedule_to_close,
                retry_policy=retry_policy,
            )
            return result
        except Exception as e:
            # Properly propagate activity errors
            if isinstance(e, exceptions.ActivityError):
                raise e.cause if e.cause else e
            raise

    async def execute(
        self,
        task: Callable[..., R] | Coroutine[Any, Any, R],
        *args,
        **kwargs,
    ) -> R | BaseException:
        """Execute multiple tasks (activities) in parallel."""

        # Must be called from within a workflow
        if not workflow.in_workflow():
            raise RuntimeError(
                "TemporalExecutor.execute must be called from within a workflow"
            )

        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            return await self._execute_task(task, *args, **kwargs)

    async def execute_many(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs,
    ) -> List[R | BaseException]:
        """Execute multiple tasks (activities) in parallel."""

        # Must be called from within a workflow
        if not workflow.in_workflow():
            raise RuntimeError(
                "TemporalExecutor.execute must be called from within a workflow"
            )

        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            return await asyncio.gather(
                *[self._execute_task(task, *args, **kwargs) for task in tasks],
                return_exceptions=True,
            )

    async def execute_streaming(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs,
    ) -> AsyncIterator[R | BaseException]:
        if not workflow.in_workflow():
            raise RuntimeError(
                "TemporalExecutor.execute_streaming must be called from within a workflow"
            )

        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            # Create futures for all tasks
            futures = [self._execute_task(task, *args, **kwargs) for task in tasks]
            pending = set(futures)

            while pending:
                done, pending = await workflow.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for future in done:
                    try:
                        result = await future
                        yield result
                    except Exception as e:
                        yield e

    async def ensure_client(self):
        """Ensure we have a connected Temporal client."""
        if self.client is None:
            self.client = await TemporalClient.connect(
                target_host=self.config.host,
                namespace=self.config.namespace,
                api_key=self.config.api_key,
                tls=self.config.tls,
                data_converter=pydantic_data_converter,
                interceptors=[TracingInterceptor(), ContextPropagationInterceptor()]
                if self.context.tracing_enabled
                else [ContextPropagationInterceptor()],
                rpc_metadata=self.config.rpc_metadata or {},
            )

        return self.client

    async def start_workflow(
        self,
        workflow_type: str,
        *args: Any,
        wait_for_result: bool = False,
        workflow_id: str | None = None,
        task_queue: str | None = None,
        workflow_memo: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> WorkflowHandle:
        """
        Starts a workflow of the given workflow type and arguments.

        Args:
            workflow_type (str): Type (class name) of the Workflow to be started.
            *workflow_args: Positional arguments to pass to the workflow.
            wait_for_result: Whether to wait for the workflow to complete and return the result.
            workflow_id: Optional workflow ID to use (instead of auto-generating).
            task_queue: Optional task queue to use (instead of default from config).
            **workflow_kwargs: Keyword arguments to pass to the workflow.

        Returns:
            If wait_for_result is True, returns the workflow result.
            Otherwise, returns a WorkflowHandle for the started workflow.
        """
        await self.ensure_client()

        # Lookup the workflow class
        wf = self.context.app.workflows.get(workflow_type)
        if not inspect.isclass(wf):
            wf = wf.__class__

        # Inspect the `run(self, …)` signature
        sig = inspect.signature(wf.run)
        # Work with a signature that excludes any leading 'self' for binding/validation
        params = [p for p in sig.parameters.values() if p.name != "self"]
        has_var_positional = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
        )
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
        sig_no_self = inspect.Signature(parameters=params)

        # Determine what to pass to the start_workflow function
        # If the workflow run is varargs/kwargs (AutoWorkflow), pass kwargs as a single payload
        if has_var_keyword or has_var_positional:
            input_arg = kwargs if kwargs else (args[0] if args else None)
        else:
            # Bind provided args/kwargs to validate and order them against signature without 'self'
            try:
                bound = sig_no_self.bind_partial(*args, **kwargs)
            except TypeError as e:
                raise ValueError(str(e))

            # Check for missing required (non-default) parameters
            for p in params:
                if p.default is inspect._empty and p.name not in bound.arguments:
                    raise ValueError(f"Missing required workflow argument '{p.name}'")

            bound_vals = [
                bound.arguments.get(p.name) for p in params if p.name in bound.arguments
            ]
            if len(bound_vals) == 0:
                input_arg = None
            elif len(bound_vals) == 1:
                input_arg = bound_vals[0]
            else:
                input_arg = bound_vals
        # Too many positionals for strict (non-varargs) run signatures?
        if not (has_var_positional or has_var_keyword):
            if len(args) > len(params):
                raise ValueError(
                    f"Got {len(args)} positional args but run() only takes {len(params)}"
                )

        # Use provided workflow_id or generate a unique one
        if workflow_id is None:
            workflow_id = f"{workflow_type}-{self.uuid()}"

        # Use provided task_queue or use the one from config
        if task_queue is None:
            task_queue = self.config.task_queue

        # Get the id reuse policy from the config, mapped to temporal enum
        id_reuse_policy = {
            "allow_duplicate": WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            "allow_duplicate_failed_only": WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
            "reject_duplicate": WorkflowIDReusePolicy.REJECT_DUPLICATE,
            "terminate_if_running": WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
        }.get(self.config.id_reuse_policy, WorkflowIDReusePolicy.ALLOW_DUPLICATE)

        # Start the workflow
        if input_arg is not None:
            handle: WorkflowHandle = await self.client.start_workflow(
                wf,
                input_arg,
                id=workflow_id,
                task_queue=task_queue,
                id_reuse_policy=id_reuse_policy,
                rpc_metadata=self.config.rpc_metadata or {},
                memo=workflow_memo or {},
            )
        else:
            handle: WorkflowHandle = await self.client.start_workflow(
                wf,
                id=workflow_id,
                task_queue=task_queue,
                id_reuse_policy=id_reuse_policy,
                rpc_metadata=self.config.rpc_metadata or {},
                memo=workflow_memo or {},
            )

        # Wait for the result if requested
        if wait_for_result:
            return await handle.result()

        return handle

    async def execute_workflow(
        self,
        workflow_type: str,
        *workflow_args: Any,
        workflow_id: str | None = None,
        task_queue: str | None = None,
        **workflow_kwargs: Any,
    ) -> Any:
        """
        Execute a workflow and wait for its result.

        This is a convenience wrapper around start_workflow with wait_for_result=True.
        """
        return await self.start_workflow(
            workflow_type,
            *workflow_args,
            wait_for_result=True,
            workflow_id=workflow_id,
            task_queue=task_queue,
            **workflow_kwargs,
        )

    def create_human_input_request(self, request: dict) -> HumanInputRequest:
        """
        Create a human input request from the arguments.

        Args:
            request: Optional arguments to include in the request.

        Returns:
            A HumanInputRequest object with workflow_id and run_id populated.
        """
        return HumanInputRequest(
            **request,
            workflow_id=workflow.info().workflow_id,
            run_id=workflow.info().run_id,
        )

    async def terminate_workflow(
        self,
        workflow_id: str,
        run_id: str | None = None,
        reason: str | None = "Cancellation",
    ) -> None:
        """
        Terminate a workflow execution.

        Args:
            workflow_id (str): Identifier of the workflow to terminate.
            run_id (Optional[str]): If provided, terminates the specific run.
                                Otherwise terminates the latest run.
            reason (Optional[str]): A reason for the termination.
        """
        await self.ensure_client()
        workflow_handle = self.client.get_workflow_handle(
            workflow_id=workflow_id, run_id=run_id
        )
        await workflow_handle.terminate(reason=reason)

    def uuid(self) -> "UUID":
        """
        Generate a UUID using Temporal's deterministic UUID generator.
        """
        try:
            return workflow.uuid4()
        except exceptions.TemporalError:
            return super().uuid()

    def random(self) -> "Random":
        """
        Get an instance of Temporal's deterministic pseudo-random number generator.

        Note, this random number generator is not cryptographically safe and should
        not be used for security purposes.

        Returns:
            The deterministically-seeded pseudo-random number generator.
        """
        try:
            return workflow.random()
        except exceptions.TemporalError:
            return super().random()


@asynccontextmanager
async def create_temporal_worker_for_app(app: "MCPApp"):
    """
    Create a Temporal worker for the given app.
    """
    activities = []

    # Initialize the app to set up the context and executor
    async with app.run() as running_app:
        if not isinstance(running_app.executor, TemporalExecutor):
            raise ValueError("App executor is not a TemporalExecutor.")

        await running_app.executor.ensure_client()

        from mcp_agent.agents.agent import AgentTasks

        agent_tasks = AgentTasks(context=running_app.context)
        app.workflow_task()(agent_tasks.call_tool_task)
        app.workflow_task()(agent_tasks.get_capabilities_task)
        app.workflow_task()(agent_tasks.get_prompt_task)
        app.workflow_task()(agent_tasks.initialize_aggregator_task)
        app.workflow_task()(agent_tasks.list_prompts_task)
        app.workflow_task()(agent_tasks.list_tools_task)
        app.workflow_task()(agent_tasks.shutdown_aggregator_task)

        # Collect activities from the global registry
        activity_registry = running_app.context.task_registry

        # Register system activities (logging, human input proxy, generic relays)
        system_activities = SystemActivities(context=running_app.context)
        app.workflow_task(name="mcp_forward_log")(system_activities.forward_log)
        app.workflow_task(name="mcp_request_user_input")(
            system_activities.request_user_input
        )
        app.workflow_task(name="mcp_relay_notify")(system_activities.relay_notify)
        app.workflow_task(name="mcp_relay_request")(system_activities.relay_request)

        for name in activity_registry.list_activities():
            activities.append(activity_registry.get_activity(name))

        # Collect workflows from the registered workflows
        workflows = running_app.context.app.workflows.values()

        worker = Worker(
            client=running_app.executor.client,
            task_queue=running_app.executor.config.task_queue,
            activities=activities,
            workflows=workflows,
            interceptors=[ContextPropagationInterceptor()],
        )

        try:
            # Yield the worker to allow the caller to use it
            yield worker
        finally:
            # No explicit cleanup needed here as the app context will handle it
            # when the async with block exits
            pass
