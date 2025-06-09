import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Dict, Generic, List, Optional, TYPE_CHECKING

from temporalio import exceptions, workflow

from mcp_agent.executor.workflow_signal import BaseSignalHandler, Signal, SignalValueT
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.executor.temporal import TemporalExecutor
    from mcp_agent.executor.workflow import Workflow

logger = get_logger(__name__)


@dataclass(slots=True)
class _Record(Generic[SignalValueT]):
    """Record for tracking signal values with versioning for broadcast semantics"""

    value: Optional[SignalValueT] = None
    version: int = 0  # monotonic counter


class SignalMailbox(Generic[SignalValueT]):
    """
    Deterministic broadcast mailbox that stores signal values with versioning.
    Each workflow run has its own mailbox instance.
    """

    def __init__(self) -> None:
        self._store: Dict[str, _Record[SignalValueT]] = {}

    def push(self, name: str, value: SignalValueT) -> None:
        """
        Store a signal value and increment its version counter.
        This enables broadcast semantics where all waiters see the same value.
        """
        rec = self._store.setdefault(name, _Record())
        rec.value = value
        rec.version += 1

        logger.debug(
            f"SignalMailbox.push: name={name}, value={value}, version={rec.version}"
        )

    def version(self, name: str) -> int:
        """Get the current version counter for a signal name"""
        return self._store.get(name, _Record()).version

    def value(self, name: str) -> SignalValueT:
        """
        Get the current value for a signal name

        Returns:
            The signal value

        Raises:
            ValueError: If no value exists for the signal
        """
        value = self._store.get(name, _Record()).value

        if value is None:
            raise ValueError(f"No value for signal {name}")

        logger.debug(
            f"SignalMailbox.value: name={name}, value={value}, version={self._store.get(name, _Record()).version}"
        )

        return value


class TemporalSignalHandler(BaseSignalHandler[SignalValueT]):
    """
    Temporal-based signal handling using workflow signals.

    This implementation uses a mailbox to store signal values and version counters
    to track new signals. It allows for dynamic signal handling and supports
    waiting for signals.
    """

    def __init__(self, executor: Optional["TemporalExecutor"] = None) -> None:
        super().__init__()
        self._executor = executor

        # Use ContextVar with default=None for safely storing and retrieving the mailbox reference
        self._mailbox_ref: ContextVar[Optional[SignalMailbox]] = ContextVar(
            "mb", default=None
        )

    def attach_to_workflow(self, wf_instance: "Workflow") -> None:
        """
        Attach this signal handler to a workflow instance.
        Registers a single dynamic signal handler for all signals.

        Args:
            wf_instance: The workflow instance to attach to

        Note:
            If the workflow already has a dynamic signal handler registered through
            @workflow.signal(dynamic=True), a Temporal runtime error will occur.
        """
        # Avoid re-registering signals - set flag early for idempotency
        if getattr(wf_instance, "_signal_handler_attached", False):
            logger.debug(
                f"Signal handler already attached to {wf_instance.name}, skipping"
            )
            return

        logger.debug(f"Attaching signal handler to workflow {wf_instance.name}")

        # Mark as attached early to ensure idempotency even if an error occurs
        wf_instance._signal_handler_attached = True

        # Get the workflow instance's mailbox
        mb: SignalMailbox = wf_instance._signal_mailbox

        # Store reference in ContextVar for wait_for_signal
        self._mailbox_ref.set(mb)

    async def wait_for_signal(
        self,
        signal: Signal[SignalValueT],
        timeout_seconds: int | None = None,
        min_version: int | None = None,
    ) -> SignalValueT:
        """
        Wait for a signal to be received.

        Args:
            signal: The signal to wait for
            timeout_seconds: Optional timeout in seconds
            min_version: Optional minimum version to wait for (defaults to current version).
                This is useful for waiting for a new signal even if one with the same name
                was already received.

        Returns:
            The emitted signal payload.

        Raises:
            RuntimeError: If called outside a workflow or mailbox not initialized
            TimeoutError: If timeout is reached
            ValueError: If no value exists for the signal after waiting
        """
        if not workflow._Runtime.current():
            raise RuntimeError("wait_for_signal must be called from within a workflow")

        # Get the mailbox safely from ContextVar
        mailbox = self._mailbox_ref.get()
        if mailbox is None:
            raise RuntimeError(
                "Signal mailbox not initialized for this workflow. Please call attach_to_workflow first."
            )

        # Get current version (no early return to avoid infinite loops)
        current_ver = (
            min_version if min_version is not None else mailbox.version(signal.name)
        )

        logger.debug(
            f"SignalMailbox.wait_for_signal: name={signal.name}, current_ver={current_ver}, min_version={min_version}"
        )

        # Wait for a new version (version > current_ver)
        try:
            await workflow.wait_condition(
                lambda: mailbox.version(signal.name) > current_ver,
                timeout=timedelta(seconds=timeout_seconds) if timeout_seconds else None,
            )

            logger.debug(
                f"SignalMailbox.wait_for_signal returned: name={signal.name}, val={mailbox.value(signal.name)}"
            )

            return mailbox.value(signal.name)
        except exceptions.TimeoutError as e:
            raise TimeoutError(f"Timeout waiting for signal {signal.name}") from e

    async def wait_for_any_signal(
        self,
        signal_names: List[str],
        workflow_id: str,
        run_id: str | None = None,
        timeout_seconds: int | None = None
    ) -> Signal[SignalValueT]:
        """
        Waits for any of the specified signals using Temporal-safe primitives.
        """
        if not workflow._Runtime.current():
            raise RuntimeError("wait_for_any_signal must be called from within a Temporal workflow")

        # Get the mailbox safely from ContextVar
        mailbox = self._mailbox_ref.get()
        if mailbox is None:
            raise RuntimeError(
                "Signal mailbox not initialized for this workflow. Please call attach_to_workflow first."
            )

        # Get current versions for all signals
        current_versions = {name: mailbox.version(name) for name in signal_names}
        
        logger.debug(
            f"SignalMailbox.wait_for_any_signal: signal_names={signal_names}, current_versions={current_versions}"
        )

        # Wait for any signal to have a new version
        def any_signal_updated():
            for name in signal_names:
                if mailbox.version(name) > current_versions[name]:
                    return True
            return False

        try:
            await workflow.wait_condition(
                any_signal_updated,
                timeout=timedelta(seconds=timeout_seconds) if timeout_seconds else None,
            )

            # Find which signal was updated
            for name in signal_names:
                if mailbox.version(name) > current_versions[name]:
                    # Just get the value directly like wait_for_signal does
                    payload = mailbox.value(name)
                    
                    logger.debug(
                        f"SignalMailbox.wait_for_any_signal returned: name={name}, val={payload}"
                    )
                    return Signal(
                        name=name,
                        payload=payload,
                        workflow_id=workflow_id,
                        run_id=run_id or workflow.info().run_id
                    )
            
            # Should not reach here
            raise RuntimeError("wait_condition returned but no signal was found")
            
        except exceptions.TimeoutError as e:
            raise asyncio.TimeoutError(f"Timeout waiting for signals: {signal_names}") from e

    def on_signal(self, signal_name: str):
        """
        Decorator that registers a callback for a signal.
        The callback will be invoked when the signal is received.

        Args:
            signal_name: The name of the signal to handle
        """

        def decorator(user_cb: Callable[[Signal[SignalValueT]], Any]):
            # Store callback as (unique_name, cb) to match BaseSignalHandler's expectation
            unique_name = ""  # Empty string, not used but kept for type compatibility
            self._handlers.setdefault(signal_name, []).append((unique_name, user_cb))
            return user_cb

        return decorator

    async def signal(self, signal: Signal[SignalValueT]) -> None:
        """
        Send a signal to a running workflow.

        Args:
            signal: The signal to send

        Raises:
            ValueError: If validation fails
            RuntimeError: If executor is missing when called outside a workflow
        """
        # Validate the signal (already checks workflow_id is not None)
        self.validate_signal(signal)

        try:
            # First try the in-workflow path
            wf_handle = workflow.get_external_workflow_handle(
                workflow_id=signal.workflow_id, run_id=signal.run_id
            )
        except workflow._NotInWorkflowEventLoopError:
            # We're on a worker thread / activity
            if not self._executor:
                raise RuntimeError("TemporalExecutor reference needed to emit signals")
            await self._executor.ensure_client()
            wf_handle = self._executor.client.get_workflow_handle(
                workflow_id=signal.workflow_id, run_id=signal.run_id
            )

        # Send the signal directly to the workflow
        await wf_handle.signal(signal.name, signal.payload)

    def validate_signal(self, signal):
        super().validate_signal(signal)
        # Add TemporalSignalHandler-specific validation
        if not signal.workflow_id:
            raise ValueError(
                "A workflow_id must be provided on a Signal for Temporal signals"
            )
