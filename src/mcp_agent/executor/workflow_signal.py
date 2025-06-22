import asyncio
import uuid
from abc import abstractmethod, ABC
from typing import Any, Callable, Dict, Generic, List, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

SignalValueT = TypeVar("SignalValueT")

# TODO: saqadri - handle signals properly that works with other execution backends like Temporal as well


class Signal(BaseModel, Generic[SignalValueT]):
    """Represents a signal that can be sent to a workflow."""

    name: str
    """
    The name of the signal. This is used to identify the signal and route it to the correct handler.
    """

    description: str | None = "Workflow Signal"
    """
    A description of the signal. This can be used to provide additional context about the signal.
    """

    payload: SignalValueT | None = None
    """
    The payload of the signal. This is the data that will be sent with the signal.
    """

    metadata: Dict[str, Any] | None = None
    """
    Additional metadata about the signal. This can be used to provide extra context or information.
    """

    workflow_id: str | None = None
    """
    The ID of the workflow that this signal is associated with. 
    This is used in conjunction with the run_id to identify the specific workflow instance.
    """

    run_id: str | None = None
    """
    The unique ID for this specific workflow run to signal. 
    This is used to identify the specific instance of the workflow that this signal is associated with.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SignalRegistration(BaseModel):
    """Tracks registration of a signal handler."""

    signal_name: str
    unique_name: str
    workflow_id: str | None = None
    run_id: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SignalHandler(Protocol, Generic[SignalValueT]):
    """Protocol for handling signals."""

    @abstractmethod
    async def signal(self, signal: Signal[SignalValueT]) -> None:
        """Emit a signal to all waiting handlers and registered callbacks."""

    @abstractmethod
    async def wait_for_signal(
        self,
        signal: Signal[SignalValueT],
        timeout_seconds: int | None = None,
    ) -> SignalValueT:
        """Wait for a signal to be emitted."""

    @abstractmethod
    async def wait_for_any_signal(
        self,
        signal_names: List[str],
        workflow_id: str,
        run_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> Signal[SignalValueT]:
        """
        Waits for any of a list of signals and returns the one that fired.
        
        This method is essential for workflows that need to react to multiple
        different events concurrently.
        
        Args:
            signal_names: A list of signal names to wait for.
            workflow_id: The ID of the workflow instance to listen on.
            run_id: Optional specific run ID of the workflow.
            timeout_seconds: Optional timeout for waiting.
            
        Returns:
            A Signal object containing the name and payload of the first signal received.
            
        Raises:
            asyncio.TimeoutError: If the timeout is reached.
        """
        ...

    def on_signal(self, signal_name: str) -> Callable:
        """
        Decorator to register a handler for a signal.

        Example:
            @signal_handler.on_signal("approval_needed")
            async def handle_approval(value: str):
                print(f"Got approval signal with value: {value}")
        """


class PendingSignal(BaseModel):
    """Tracks a waiting signal handler and its event."""

    registration: SignalRegistration
    event: asyncio.Event | None = None
    value: SignalValueT | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BaseSignalHandler(ABC, Generic[SignalValueT]):
    """Base class implementing common signal handling functionality."""

    def __init__(self):
        # Map signal_name -> list of PendingSignal objects
        self._pending_signals: Dict[str, List[PendingSignal]] = {}
        # Map signal_name -> list of (unique_name, handler) tuples
        self._handlers: Dict[str, List[tuple[str, Callable]]] = {}
        self._lock = asyncio.Lock()

    async def cleanup(self, signal_name: str | None = None):
        """Clean up handlers and registrations for a signal or all signals."""
        async with self._lock:
            if signal_name:
                if signal_name in self._handlers:
                    del self._handlers[signal_name]
                if signal_name in self._pending_signals:
                    del self._pending_signals[signal_name]
            else:
                self._handlers.clear()
                self._pending_signals.clear()

    def validate_signal(self, signal: Signal[SignalValueT]):
        """Validate signal properties."""
        if not signal.name:
            raise ValueError("Signal name is required")
        # Subclasses can override to add more validation

    def on_signal(self, signal_name: str) -> Callable:
        """Register a handler for a signal."""

        def decorator(func: Callable) -> Callable:
            unique_name = f"{signal_name}_{uuid.uuid4()}"

            async def wrapped(value: SignalValueT):
                try:
                    if asyncio.iscoroutinefunction(func):
                        await func(value)
                    else:
                        func(value)
                except Exception as e:
                    # Log the error but don't fail the entire signal handling
                    print(f"Error in signal handler {signal_name}: {str(e)}")

            self._handlers.setdefault(signal_name, []).append((unique_name, wrapped))
            return wrapped

        return decorator

    @abstractmethod
    async def signal(self, signal: Signal[SignalValueT]) -> None:
        """Emit a signal to all waiting handlers and registered callbacks."""

    @abstractmethod
    async def wait_for_signal(
        self,
        signal: Signal[SignalValueT],
        timeout_seconds: int | None = None,
    ) -> SignalValueT:
        """Wait for a signal to be emitted."""


class ConsoleSignalHandler(SignalHandler[str]):
    """Simple console-based signal handling (blocks on input)."""

    def __init__(self):
        self._pending_signals: Dict[str, List[PendingSignal]] = {}
        self._handlers: Dict[str, List[Callable]] = {}

    async def wait_for_signal(self, signal, timeout_seconds=None):
        """Block and wait for console input."""
        print(f"\n[SIGNAL: {signal.name}] {signal.description}")
        if timeout_seconds:
            print(f"(Timeout in {timeout_seconds} seconds)")

        # Use asyncio.get_event_loop().run_in_executor to make input non-blocking
        loop = asyncio.get_event_loop()
        if timeout_seconds is not None:
            try:
                value = await asyncio.wait_for(
                    loop.run_in_executor(None, input, "Enter value: "), timeout_seconds
                )
            except asyncio.TimeoutError:
                print("\nTimeout waiting for input")
                raise
        else:
            value = await loop.run_in_executor(None, input, "Enter value: ")

        return value

        # value = input(f"[SIGNAL: {signal.name}] {signal.description}: ")
        # return value

    def on_signal(self, signal_name):
        def decorator(func):
            async def wrapped(value: SignalValueT):
                if asyncio.iscoroutinefunction(func):
                    await func(value)
                else:
                    func(value)

            self._handlers.setdefault(signal_name, []).append(wrapped)
            return wrapped

        return decorator

    async def wait_for_any_signal(
        self,
        signal_names: List[str],
        workflow_id: str,
        run_id: str | None = None,
        timeout_seconds: int | None = None
    ) -> Signal[SignalValueT]:
        """
        Wait for any of the specified signals using console input.
        Note: This is a simplified implementation for console-based workflows.
        """
        # For console handler, we'll just wait for the first signal name entered
        loop = asyncio.get_event_loop()
        if timeout_seconds is not None:
            try:
                signal_name = await asyncio.wait_for(
                    loop.run_in_executor(None, input, f"Enter signal name ({', '.join(signal_names)}): "), 
                    timeout_seconds
                )
            except asyncio.TimeoutError:
                print("\nTimeout waiting for input")
                raise
        else:
            signal_name = await loop.run_in_executor(None, input, f"Enter signal name ({', '.join(signal_names)}): ")
        
        # Validate the signal name
        if signal_name not in signal_names:
            raise ValueError(f"Invalid signal name: {signal_name}. Expected one of: {signal_names}")
        
        # Get the payload
        payload = await loop.run_in_executor(None, input, f"Enter payload for {signal_name}: ")
        
        return Signal(
            name=signal_name,
            payload=payload,
            workflow_id=workflow_id,
            run_id=run_id
        )

    async def signal(self, signal):
        print(f"[SIGNAL SENT: {signal.name}] Value: {signal.payload}")

        handlers = self._handlers.get(signal.name, [])
        await asyncio.gather(
            *(handler(signal) for handler in handlers), return_exceptions=True
        )

        # Notify any waiting coroutines
        if signal.name in self._pending_signals:
            for ps in self._pending_signals[signal.name]:
                ps.value = signal.payload
                ps.event.set()


class AsyncioSignalHandler(BaseSignalHandler[SignalValueT]):
    """
    Asyncio-based signal handling using an internal dictionary of asyncio Events.
    """

    async def wait_for_signal(
        self, signal, timeout_seconds: int | None = None
    ) -> SignalValueT:
        event = asyncio.Event()
        unique_signal_name = f"{signal.name}_{uuid.uuid4()}"

        registration = SignalRegistration(
            signal_name=signal.name,
            unique_name=unique_signal_name,
            workflow_id=signal.workflow_id,
            run_id=signal.run_id,
        )

        pending_signal = PendingSignal(registration=registration, event=event)

        async with self._lock:
            # Add to pending signals
            self._pending_signals.setdefault(signal.name, []).append(pending_signal)

        try:
            # Wait for signal
            if timeout_seconds is not None:
                await asyncio.wait_for(event.wait(), timeout_seconds)
            else:
                await event.wait()

            return pending_signal.value
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"Timeout waiting for signal {signal.name}") from e
        finally:
            async with self._lock:
                # Remove from pending signals
                if signal.name in self._pending_signals:
                    self._pending_signals[signal.name] = [
                        ps
                        for ps in self._pending_signals[signal.name]
                        if ps.registration.unique_name != unique_signal_name
                    ]
                    if not self._pending_signals[signal.name]:
                        del self._pending_signals[signal.name]

    def on_signal(self, signal_name):
        def decorator(func):
            unique_signal_name = f"{signal_name}_{uuid.uuid4()}"

            async def wrapped(value: SignalValueT):
                if asyncio.iscoroutinefunction(func):
                    await func(value)
                else:
                    func(value)

            self._handlers.setdefault(signal_name, []).append(
                [unique_signal_name, wrapped]
            )
            return wrapped

        return decorator

    async def wait_for_any_signal(
        self,
        signal_names: List[str],
        workflow_id: str,
        run_id: str | None = None,
        timeout_seconds: int | None = None
    ) -> Signal[SignalValueT]:
        """
        Waits for any of a list of signals using asyncio primitives.
        """
        # Create an event and a registration for each signal
        pending_signals: List[PendingSignal] = []
        waiter_tasks: List[asyncio.Task] = []
        
        async with self._lock:
            for name in signal_names:
                event = asyncio.Event()
                unique_name = f"{name}_{uuid.uuid4()}"
                registration = SignalRegistration(
                    signal_name=name,
                    unique_name=unique_name,
                    workflow_id=workflow_id,
                    run_id=run_id,
                )
                pending = PendingSignal(registration=registration, event=event)
                pending_signals.append(pending)
                self._pending_signals.setdefault(name, []).append(pending)
                waiter_tasks.append(asyncio.create_task(event.wait()))

        try:
            # Wait for any of the events to be set
            done, pending = await asyncio.wait(
                waiter_tasks,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout_seconds,
            )

            if not done:
                raise asyncio.TimeoutError(f"Timeout waiting for signals: {signal_names}")

            # Find which pending signal corresponds to the completed task
            completed_task = done.pop()
            triggered_pending_signal = None
            for i, task in enumerate(waiter_tasks):
                if task is completed_task:
                    triggered_pending_signal = pending_signals[i]
                    break
            
            if not triggered_pending_signal:
                # Should not happen
                raise RuntimeError("Could not identify which signal was triggered.")

            return Signal(
                name=triggered_pending_signal.registration.signal_name,
                payload=triggered_pending_signal.value,
                workflow_id=workflow_id,
                run_id=run_id
            )

        finally:
            # Cleanup all waiters for this call
            for task in waiter_tasks:
                if not task.done():
                    task.cancel()
            
            async with self._lock:
                for pending_signal in pending_signals:
                    name = pending_signal.registration.signal_name
                    unique_name = pending_signal.registration.unique_name
                    if name in self._pending_signals:
                        self._pending_signals[name] = [
                            p for p in self._pending_signals[name]
                            if p.registration.unique_name != unique_name
                        ]
                        if not self._pending_signals[name]:
                            del self._pending_signals[name]

    async def signal(self, signal):
        async with self._lock:
            # Notify any waiting coroutines
            if signal.name in self._pending_signals:
                pending = self._pending_signals[signal.name]
                for ps in pending:
                    ps.value = signal.payload
                    ps.event.set()

        # Notify any registered handler functions
        tasks = []
        handlers = self._handlers.get(signal.name, [])
        for _, handler in handlers:
            tasks.append(handler(signal))

        await asyncio.gather(*tasks, return_exceptions=True)


# TODO: saqadri - check if we need to do anything to combine this and AsyncioSignalHandler
class LocalSignalStore:
    """
    Simple in-memory structure that allows coroutines to wait for a signal
    and triggers them when a signal is emitted.
    """

    def __init__(self):
        # For each signal_name, store a list of futures that are waiting for it
        self._waiters: Dict[str, List[asyncio.Future]] = {}

    async def emit(self, signal_name: str, payload: Any):
        # If we have waiting futures, set their result
        if signal_name in self._waiters:
            for future in self._waiters[signal_name]:
                if not future.done():
                    future.set_result(payload)
            self._waiters[signal_name].clear()

    async def wait_for(
        self, signal_name: str, timeout_seconds: int | None = None
    ) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        self._waiters.setdefault(signal_name, []).append(future)

        if timeout_seconds is not None:
            try:
                return await asyncio.wait_for(future, timeout=timeout_seconds)
            except asyncio.TimeoutError:
                # remove the fut from list
                if not future.done():
                    self._waiters[signal_name].remove(future)
                raise
        else:
            return await future


class SignalWaitCallback(Protocol):
    """Protocol for callbacks that are triggered when a workflow pauses waiting for a given signal."""

    async def __call__(
        self,
        signal_name: str,
        request_id: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Receive a notification that a workflow is pausing on a signal.

        Args:
            signal_name: The name of the signal the workflow is pausing on.
            workflow_id: The ID of the workflow that is pausing (if using a workflow engine).
            run_id: The ID of the workflow run that is pausing (if using a workflow engine).
            metadata: Additional metadata about the signal.
        """
        ...
