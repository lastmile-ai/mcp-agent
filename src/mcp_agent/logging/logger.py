"""
Logger module for the MCP Agent, which provides:
- Local + optional remote event transport
- Async event bus
- OpenTelemetry tracing decorators (for distributed tracing)
- Automatic injection of trace_id/span_id into events
- Developer-friendly Logger that can be used anywhere
"""

import asyncio
import threading
import time

from typing import Any, Dict

from contextlib import asynccontextmanager, contextmanager

from mcp_agent.logging.events import Event, EventContext, EventFilter, EventType
from mcp_agent.logging.listeners import (
    BatchingListener,
    LoggingListener,
    ProgressListener,
)
from mcp_agent.logging.transport import AsyncEventBus, EventTransport


class Logger:
    """
    Developer-friendly logger that sends events to the AsyncEventBus.
    - `type` is a broad category (INFO, ERROR, etc.).
    - `name` can be a custom domain-specific event name, e.g. "ORDER_PLACED".
    """

    def __init__(self, namespace: str, session_id: str | None = None):
        self.namespace = namespace
        self.session_id = session_id
        self.event_bus = AsyncEventBus.get()

    def _ensure_event_loop(self):
        """Ensure we have an event loop we can use."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # If no loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _emit_event(self, event: Event):
        """Emit an event by running it in the event loop."""
        loop = self._ensure_event_loop()
        try:
            is_running = loop.is_running()
        except NotImplementedError:
            # Handle Temporal workflow environment where is_running() is not implemented
            # Default to assuming the loop is not running
            is_running = False

        if is_running:
            # If we're in a thread with a running loop, schedule the coroutine
            asyncio.create_task(self.event_bus.emit(event))
        else:
            # If no loop is running, run it until the emit completes
            try:
                loop.run_until_complete(self.event_bus.emit(event))
            except NotImplementedError:
                # Handle Temporal workflow environment where run_until_complete() is not implemented
                # In Temporal, we can't block on async operations, so we'll need to avoid this
                # Simply log to stdout/stderr as a fallback
                import sys

                print(
                    f"[{event.type}] {event.namespace}: {event.message}",
                    file=sys.stderr,
                )

    def event(
        self,
        etype: EventType,
        ename: str | None,
        message: str,
        context: EventContext | None,
        data: dict,
    ):
        """Create and emit an event."""
        # Only create or modify context with session_id if we have one
        if self.session_id:
            # If no context was provided, create one with our session_id
            if context is None:
                context = EventContext(session_id=self.session_id)
            # If context exists but has no session_id, add our session_id
            elif context.session_id is None:
                context.session_id = self.session_id

        evt = Event(
            type=etype,
            name=ename,
            namespace=self.namespace,
            message=message,
            context=context,
            data=data,
        )
        self._emit_event(evt)

    def debug(
        self,
        message: str,
        name: str | None = None,
        context: EventContext = None,
        **data,
    ):
        """Log a debug message."""
        self.event("debug", name, message, context, data)

    def info(
        self,
        message: str,
        name: str | None = None,
        context: EventContext = None,
        **data,
    ):
        """Log an info message."""
        self.event("info", name, message, context, data)

    def warning(
        self,
        message: str,
        name: str | None = None,
        context: EventContext = None,
        **data,
    ):
        """Log a warning message."""
        self.event("warning", name, message, context, data)

    def error(
        self,
        message: str,
        name: str | None = None,
        context: EventContext = None,
        **data,
    ):
        """Log an error message."""
        self.event("error", name, message, context, data)

    def progress(
        self,
        message: str,
        name: str | None = None,
        percentage: float = None,
        context: EventContext = None,
        **data,
    ):
        """Log a progress message."""
        merged_data = dict(percentage=percentage, **data)
        self.event("progress", name, message, context, merged_data)


@contextmanager
def event_context(
    logger: Logger,
    message: str,
    event_type: EventType = "info",
    name: str | None = None,
    **data,
):
    """
    Times a synchronous block, logs an event after completion.
    Because logger methods are async, we schedule the final log.
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time

        logger.event(
            event_type,
            name,
            f"{message} finished in {duration:.3f}s",
            None,
            {"duration": duration, **data},
        )


# TODO: saqadri - check if we need this
@asynccontextmanager
async def async_event_context(
    logger: Logger,
    message: str,
    event_type: EventType = "info",
    name: str | None = None,
    **data,
):
    """
    Times an asynchronous block, logs an event after completion.
    Because logger methods are async, we schedule the final log.
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        logger.event(
            event_type,
            name,
            f"{message} finished in {duration:.3f}s",
            None,
            {"duration": duration, **data},
        )


class LoggingConfig:
    """Global configuration for the logging system."""

    _initialized = False

    @classmethod
    async def configure(
        cls,
        event_filter: EventFilter | None = None,
        transport: EventTransport | None = None,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        **kwargs: Any,
    ):
        """
        Configure the logging system.

        Args:
            event_filter: Default filter for all loggers
            transport: Transport for sending events to external systems
            batch_size: Default batch size for batching listener
            flush_interval: Default flush interval for batching listener
            **kwargs: Additional configuration options
        """
        if cls._initialized:
            return

        bus = AsyncEventBus.get(transport=transport)

        # Add standard listeners
        if "logging" not in bus.listeners:
            bus.add_listener("logging", LoggingListener(event_filter=event_filter))

        # Only add progress listener if enabled in settings
        if "progress" not in bus.listeners and kwargs.get("progress_display", True):
            bus.add_listener(
                "progress",
                ProgressListener(token_counter=kwargs.get("token_counter", None)),
            )

        if "batching" not in bus.listeners:
            bus.add_listener(
                "batching",
                BatchingListener(
                    event_filter=event_filter,
                    batch_size=batch_size,
                    flush_interval=flush_interval,
                ),
            )

        await bus.start()
        cls._initialized = True

    @classmethod
    async def shutdown(cls):
        """Shutdown the logging system gracefully."""
        if not cls._initialized:
            return
        bus = AsyncEventBus.get()
        await bus.stop()
        cls._initialized = False

    @classmethod
    @asynccontextmanager
    async def managed(cls, **config_kwargs):
        """Context manager for the logging system lifecycle."""
        try:
            await cls.configure(**config_kwargs)
            yield
        finally:
            await cls.shutdown()


_logger_lock = threading.Lock()
_loggers: Dict[str, Logger] = {}


def get_logger(namespace: str, session_id: str | None = None) -> Logger:
    """
    Get a logger instance for a given namespace.
    Creates a new logger if one doesn't exist for this namespace.

    Args:
        namespace: The namespace for the logger (e.g. "agent.helper", "workflow.demo")
        session_id: Optional session ID to associate with all events from this logger

    Returns:
        A Logger instance for the given namespace
    """

    with _logger_lock:
        # Create a new logger if one doesn't exist
        if namespace not in _loggers:
            _loggers[namespace] = Logger(namespace, session_id)
        return _loggers[namespace]
