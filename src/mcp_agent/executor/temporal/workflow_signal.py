from contextvars import ContextVar
from datetime import timedelta
from typing import Any, Callable, Optional, TYPE_CHECKING

from temporalio import exceptions, workflow

from mcp_agent.executor.workflow_signal import (
    BaseSignalHandler,
    Signal,
    SignalValueT,
    SignalMailbox,
)
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.executor.temporal import TemporalExecutor
    from mcp_agent.executor.workflow import Workflow

logger = get_logger(__name__)


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
        if not workflow.in_workflow():
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

        if workflow.in_workflow():
            workflow_info = workflow.info()
            if (
                signal.workflow_id == workflow_info.workflow_id
                and signal.run_id == workflow_info.run_id
            ):
                # We're already in the workflow that should receive the signal. Temporal does not allow
                # sending signals to the same workflow from within itself, so we handle it directly.
                # Ref: https://github.com/temporalio/temporal/issues/682
                logger.debug("Already in the target workflow, sending signal directly")

                mailbox = self._mailbox_ref.get()
                if mailbox is None:
                    raise RuntimeError(
                        "Signal mailbox not initialized for this workflow. Please call attach_to_workflow first."
                    )

                mailbox.push(signal.name, signal.payload)
                return

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
        if signal.workflow_id is None or signal.run_id is None:
            raise ValueError(
                "No workflow_id or run_id provided on Signal. That is required for Temporal signals"
            )
