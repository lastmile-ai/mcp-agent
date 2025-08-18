import asyncio
import functools
import random
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    TYPE_CHECKING,
)

from mcp_agent.human_input.types import HumanInputRequest
from pydantic import BaseModel, ConfigDict

from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.executor.workflow_signal import (
    AsyncioSignalHandler,
    Signal,
    SignalHandler,
    SignalValueT,
)
from mcp_agent.logging.logger import get_logger
from mcp_agent.tracing.telemetry import telemetry

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)

# Type variable for the return type of tasks
R = TypeVar("R")


class ExecutorConfig(BaseModel):
    """Configuration for executors."""

    max_concurrent_activities: int | None = None  # Unbounded by default
    timeout_seconds: timedelta | None = None  # No timeout by default
    retry_policy: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class Executor(ABC, ContextDependent):
    """Abstract base class for different execution backends"""

    def __init__(
        self,
        engine: str,
        config: ExecutorConfig | None = None,
        signal_bus: SignalHandler = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(context=context, **kwargs)
        self.execution_engine = engine

        if config:
            self.config = config
        else:
            # TODO: saqadri - executor config should be loaded from settings
            # ctx = get_current_context()
            self.config = ExecutorConfig()

        self.signal_bus = signal_bus

    @asynccontextmanager
    async def execution_context(self):
        """Context manager for execution setup/teardown."""
        try:
            yield
        except Exception as e:
            # TODO: saqadri - add logging or other error handling here
            raise e

    @abstractmethod
    async def execute(
        self,
        task: Callable[..., R] | Coroutine[Any, Any, R],
        *args,
        **kwargs,
    ) -> R | BaseException:
        """Execute a list of tasks and return their results"""

    @abstractmethod
    async def execute_many(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs,
    ) -> List[R | BaseException]:
        """Execute a list of tasks and return their results"""

    @abstractmethod
    async def execute_streaming(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs: Any,
    ) -> AsyncIterator[R | BaseException]:
        """Execute tasks and yield results as they complete"""

    @abstractmethod
    def create_human_input_request(
        self,
        request: dict,
    ) -> HumanInputRequest:
        """Create a HumanInputRequest for the given request."""

    async def map(
        self,
        func: Callable[..., R],
        inputs: List[Any],
        **kwargs: Any,
    ) -> List[R | BaseException]:
        """
        Run `func(item)` for each item in `inputs` with concurrency limit.
        """
        results: List[R, BaseException] = []

        async def run(item):
            if self.config.max_concurrent_activities:
                semaphore = asyncio.Semaphore(self.config.max_concurrent_activities)
                async with semaphore:
                    return await self.execute(functools.partial(func, item), **kwargs)
            else:
                return await self.execute(functools.partial(func, item), **kwargs)

        coros = [run(x) for x in inputs]
        # gather all, each returns a single-element list
        list_of_lists = await asyncio.gather(*coros, return_exceptions=True)

        # Flatten results
        for entry in list_of_lists:
            if isinstance(entry, list):
                results.extend(entry)
            else:
                # Means we got an exception at the gather level
                results.append(entry)

        return results

    async def validate_task(
        self, task: Callable[..., R] | Coroutine[Any, Any, R]
    ) -> None:
        """Validate a task before execution."""
        if not (asyncio.iscoroutine(task) or asyncio.iscoroutinefunction(task)):
            raise TypeError(f"Task must be async: {task}")

    async def signal(
        self,
        signal_name: str,
        payload: SignalValueT = None,
        signal_description: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """
        Emit a signal.

        Args:
            signal_name: The name of the signal to emit
            payload: Optional data to include with the signal
            signal_description: Optional human-readable description
            workflow_id: Optional workflow ID to send the signal
            run_id: Optional run ID of the workflow instance to signal
        """
        signal = Signal[SignalValueT](
            name=signal_name,
            payload=payload,
            description=signal_description,
            workflow_id=workflow_id,
            run_id=run_id,
        )
        await self.signal_bus.signal(signal)

    async def wait_for_signal(
        self,
        signal_name: str,
        request_id: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
        signal_description: str | None = None,
        timeout_seconds: int | None = None,
        signal_type: Type[SignalValueT] = str,
    ) -> SignalValueT:
        """
        Wait until a signal with signal_name is emitted (or timeout).
        Return the signal's payload when triggered, or raise on timeout.
        """

        # Notify any callbacks that the workflow is about to be paused waiting for a signal
        if self.context.signal_notification:
            self.context.signal_notification(
                signal_name=signal_name,
                request_id=request_id,
                workflow_id=workflow_id,
                run_id=run_id,
                metadata={
                    "description": signal_description,
                    "timeout_seconds": timeout_seconds,
                    "signal_type": signal_type,
                },
            )

        signal = Signal[signal_type](
            name=signal_name,
            description=signal_description,
            workflow_id=workflow_id,
            run_id=run_id,
        )
        return await self.signal_bus.wait_for_signal(signal)

    def uuid(self) -> uuid.UUID:
        """
        Generate a UUID. Some executors enforce deterministic UUIDs, so this is an
        opportunity for an executor to provide its own UUID generation.

        Defaults to uuid4().
        """
        return uuid.uuid4()

    def random(self) -> random.Random:
        """
        Get a random number generator. Some executors enforce deterministic random
        number generation, so this is an opportunity for an executor to provide its
        own random number generator.

        Defaults to random.Random().
        """
        return random.Random()


class AsyncioExecutor(Executor):
    """Default executor using asyncio"""

    def __init__(
        self,
        config: ExecutorConfig | None = None,
        signal_bus: SignalHandler | None = None,
    ):
        signal_bus = signal_bus or AsyncioSignalHandler()
        super().__init__(engine="asyncio", config=config, signal_bus=signal_bus)

        self._activity_semaphore: asyncio.Semaphore | None = None
        if self.config.max_concurrent_activities is not None:
            self._activity_semaphore = asyncio.Semaphore(
                self.config.max_concurrent_activities
            )

    async def _execute_task(
        self, task: Callable[..., R] | Coroutine[Any, Any, R], *args, **kwargs
    ) -> R | BaseException:
        async def run_task(task: Callable[..., R] | Coroutine[Any, Any, R]) -> R:
            try:
                if asyncio.iscoroutine(task):
                    return await task
                elif asyncio.iscoroutinefunction(task):
                    return await task(*args, **kwargs)
                else:
                    # Execute the callable and await if it returns a coroutine
                    loop = asyncio.get_running_loop()

                    # Using partial to handle both args and kwargs together
                    wrapped_task = functools.partial(task, *args, **kwargs)
                    result = await loop.run_in_executor(None, wrapped_task)

                    # Handle case where the sync function returns a coroutine
                    if asyncio.iscoroutine(result):
                        return await result

                    return result
            except Exception as e:
                logger.error(f"Error executing task: {e}")
                return e

        if self._activity_semaphore:
            async with self._activity_semaphore:
                return await run_task(task)
        else:
            return await run_task(task)

    @telemetry.traced()
    async def execute(
        self,
        task: Callable[..., R] | Coroutine[Any, Any, R],
        *args,
        **kwargs,
    ) -> R | BaseException:
        """
        Execute a task and return its results.

        Args:
            task: The task to execute
            *args: Positional arguments to pass to the task
            **kwargs: Additional arguments to pass to the tasks

        Returns:
            A result or exception
        """
        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            return await self._execute_task(
                task,
                *args,
                **kwargs,
            )

    @telemetry.traced()
    async def execute_many(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs,
    ) -> List[R | BaseException]:
        """
        Execute a list of tasks and return their results.

        Args:
            tasks: The tasks to execute
            *args: Positional arguments to pass to each task
            **kwargs: Additional arguments to pass to the tasks

        Returns:
            A list of results or exceptions
        """
        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            return await asyncio.gather(
                *(
                    self._execute_task(
                        task,
                        **kwargs,
                    )
                    for task in tasks
                ),
                return_exceptions=True,
            )

    @telemetry.traced()
    async def execute_streaming(
        self,
        tasks: List[Callable[..., R] | Coroutine[Any, Any, R]],
        *args,
        **kwargs: Any,
    ) -> AsyncIterator[R | BaseException]:
        """
        Execute tasks and yield results as they complete.

        Args:
            tasks: The tasks to execute
            *args: Positional arguments to pass to each task
            **kwargs: Additional arguments to pass to the tasks

        Yields:
            Results or exceptions as tasks complete
        """
        # TODO: saqadri - validate if async with self.execution_context() is needed here
        async with self.execution_context():
            # Create futures for all tasks
            futures = [
                asyncio.create_task(
                    self._execute_task(
                        task,
                        *args,
                        **kwargs,
                    )
                )
                for task in tasks
            ]
            pending = set(futures)

            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for future in done:
                    yield await future

    @telemetry.traced()
    async def signal(
        self,
        signal_name: str,
        payload: SignalValueT = None,
        signal_description: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        await super().signal(
            signal_name, payload, signal_description, workflow_id, run_id
        )

    @telemetry.traced()
    async def wait_for_signal(
        self,
        signal_name: str,
        request_id: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
        signal_description: str | None = None,
        timeout_seconds: int | None = None,
        signal_type: Type[SignalValueT] = str,
    ) -> SignalValueT:
        return await super().wait_for_signal(
            signal_name,
            request_id,
            workflow_id,
            run_id,
            signal_description,
            timeout_seconds,
            signal_type,
        )

    def create_human_input_request(self, request: dict) -> HumanInputRequest:
        """
        Create a human input request from the arguments.

        Args:
            request: Optional arguments to include in the request.

        Returns:
            A HumanInputRequest object.
        """
        return HumanInputRequest(**request)
