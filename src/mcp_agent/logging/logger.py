"""
Logger module for the MCP Agent, which provides:
- Local + optional remote event transport
- Async event bus
- OpenTelemetry tracing decorators (for distributed tracing)
- Automatic injection of trace_id/span_id into events
- Developer-friendly Logger that can be used anywhere
"""

import asyncio
from datetime import timedelta
import threading
import time

from typing import Any, Dict, Final

from contextlib import asynccontextmanager, contextmanager


from mcp_agent.logging.events import (
    Event,
    EventContext,
    EventFilter,
    EventType,
)
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

    def __init__(
        self, namespace: str, session_id: str | None = None, bound_context=None
    ):
        self.namespace = namespace
        self.session_id = session_id
        self.event_bus = AsyncEventBus.get()
        # Optional reference to an application/context object that may carry
        # an "upstream_session" attribute. This allows cached loggers to
        # observe the current upstream session without relying on globals.
        self._bound_context = bound_context

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
            # Detect Temporal workflow runtime without hard dependency
            # If inside Temporal workflow sandbox, avoid run_until_complete and use workflow-safe forwarding
            in_temporal_workflow = False
            try:
                from temporalio import workflow as _wf  # type: ignore

                try:
                    in_temporal_workflow = bool(_wf.in_workflow())
                except Exception:
                    in_temporal_workflow = False
            except Exception:
                in_temporal_workflow = False

            if in_temporal_workflow:
                # Prefer forwarding via the upstream session proxy using a workflow task, if available.
                try:
                    from mcp_agent.executor.temporal.temporal_context import (
                        get_execution_id as _get_exec_id,
                    )

                    upstream = getattr(event, "upstream_session", None)
                    if (
                        upstream is None
                        and getattr(self, "_bound_context", None) is not None
                    ):
                        try:
                            upstream = getattr(
                                self._bound_context, "upstream_session", None
                            )
                        except Exception:
                            upstream = None

                    # Construct payload
                    async def _forward_via_proxy():
                        # If we have an upstream session, use it first
                        if upstream is not None:
                            try:
                                level_map = {
                                    "debug": "debug",
                                    "info": "info",
                                    "warning": "warning",
                                    "error": "error",
                                    "progress": "info",
                                }
                                level = level_map.get(event.type, "info")
                                logger_name = (
                                    event.namespace
                                    if not event.name
                                    else f"{event.namespace}.{event.name}"
                                )
                                data = {
                                    "message": event.message,
                                    "namespace": event.namespace,
                                    "name": event.name,
                                    "timestamp": event.timestamp.isoformat(),
                                }
                                if event.data:
                                    data["data"] = event.data
                                if event.trace_id or event.span_id:
                                    data["trace"] = {
                                        "trace_id": event.trace_id,
                                        "span_id": event.span_id,
                                    }
                                if event.context is not None:
                                    data["context"] = event.context.model_dump()

                                await upstream.send_log_message(  # type: ignore[attr-defined]
                                    level=level, data=data, logger=logger_name
                                )
                                return
                            except Exception:
                                pass

                        # Fallback: use activity gateway directly if execution_id is available
                        try:
                            exec_id = _get_exec_id()
                            if exec_id:
                                level = {
                                    "debug": "debug",
                                    "info": "info",
                                    "warning": "warning",
                                    "error": "error",
                                    "progress": "info",
                                }.get(event.type, "info")
                                ns = event.namespace
                                msg = event.message
                                data = event.data or {}
                                # Call by activity name to align with worker registration
                                await _wf.execute_activity(
                                    "mcp_forward_log",
                                    exec_id,
                                    level,
                                    ns,
                                    msg,
                                    data,
                                    schedule_to_close_timeout=timedelta(seconds=5),
                                )
                                return
                        except Exception:
                            pass

                        # If all else fails, fall back to stderr transport
                        self.event_bus.emit_with_stderr_transport(event)

                    try:
                        _wf.create_task(_forward_via_proxy())
                        return
                    except Exception:
                        # Could not create workflow task, fall through to stderr transport
                        pass
                except Exception:
                    # If Temporal workflow module unavailable or any error occurs, fall through
                    pass

                # As a last resort, log to stdout/stderr as a fallback
                self.event_bus.emit_with_stderr_transport(event)
            else:
                try:
                    loop.run_until_complete(self.event_bus.emit(event))
                except NotImplementedError:
                    pass

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

        # Attach upstream_session to the event so the upstream listener
        # can forward reliably, regardless of the current task context.
        # 1) Prefer logger-bound app context (set at creation or refreshed by caller)
        extra_event_fields: Dict[str, Any] = {}

        try:
            upstream = (
                getattr(self._bound_context, "upstream_session", None)
                if getattr(self, "_bound_context", None) is not None
                else None
            )
            if upstream is not None:
                extra_event_fields["upstream_session"] = upstream
        except Exception:
            pass
        # Fallback to default bound context if logger wasn't explicitly bound
        if (
            "upstream_session" not in extra_event_fields
            and _default_bound_context is not None
        ):
            try:
                upstream = getattr(_default_bound_context, "upstream_session", None)
                if upstream is not None:
                    extra_event_fields["upstream_session"] = upstream
            except Exception:
                pass

        # Do not use global context fallbacks here; they are unsafe under concurrency.

        # No further fallbacks; upstream forwarding must be enabled by passing
        # a bound context when creating the logger or by server code attaching
        # upstream_session to the application context.

        evt = Event(
            type=etype,
            name=ename,
            namespace=self.namespace,
            message=message,
            context=context,
            data=data,
            **extra_event_fields,
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

    _initialized: bool = False
    _event_filter_ref: EventFilter | None = None

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
        bus = AsyncEventBus.get(transport=transport)
        # Keep a reference to the provided filter so we can update at runtime
        if event_filter is not None:
            cls._event_filter_ref = event_filter

        # If already initialized, ensure critical listeners exist and return
        if cls._initialized:
            # Forward logs upstream via MCP notifications if upstream_session is configured
            try:
                from mcp_agent.logging.listeners import MCPUpstreamLoggingListener

                has_upstream_listener = any(
                    isinstance(listener, MCPUpstreamLoggingListener)
                    for listener in bus.listeners.values()
                )
                if not has_upstream_listener:
                    from typing import Final as _Final

                    MCP_UPSTREAM_LISTENER_NAME: _Final[str] = "mcp_upstream"
                    bus.add_listener(
                        MCP_UPSTREAM_LISTENER_NAME,
                        MCPUpstreamLoggingListener(event_filter=cls._event_filter_ref),
                    )
            except Exception:
                pass
            return

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

        # Forward logs upstream via MCP notifications if upstream_session is configured
        # Avoid duplicate registration by checking existing instances, not key name.
        try:
            from mcp_agent.logging.listeners import MCPUpstreamLoggingListener

            has_upstream_listener = any(
                isinstance(listener, MCPUpstreamLoggingListener)
                for listener in bus.listeners.values()
            )
            if not has_upstream_listener:
                MCP_UPSTREAM_LISTENER_NAME: Final[str] = "mcp_upstream"
                bus.add_listener(
                    MCP_UPSTREAM_LISTENER_NAME,
                    MCPUpstreamLoggingListener(event_filter=event_filter),
                )
        except Exception:
            # Non-fatal if import fails
            pass

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
    def set_min_level(cls, level: EventType | str) -> None:
        """Update the minimum logging level on the shared event filter, if available."""
        if cls._event_filter_ref is None:
            return
        # Normalize level
        normalized = str(level).lower()
        # Map synonyms to our EventType scale
        mapping: Dict[str, EventType] = {
            "debug": "debug",
            "info": "info",
            "notice": "info",
            "warning": "warning",
            "warn": "warning",
            "error": "error",
            "critical": "error",
            "alert": "error",
            "emergency": "error",
        }
        cls._event_filter_ref.min_level = mapping.get(normalized, "info")

    @classmethod
    def get_event_filter(cls) -> EventFilter | None:
        return cls._event_filter_ref

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
_default_bound_context: Any | None = None


def get_logger(namespace: str, session_id: str | None = None, context=None) -> Logger:
    """
    Get a logger instance for a given namespace.
    Creates a new logger if one doesn't exist for this namespace.

    Args:
        namespace: The namespace for the logger (e.g. "agent.helper", "workflow.demo")
        session_id: Optional session ID to associate with all events from this logger
        context: Deprecated/ignored. Present for backwards compatibility.

    Returns:
        A Logger instance for the given namespace
    """

    with _logger_lock:
        existing = _loggers.get(namespace)
        if existing is None:
            bound_ctx = context if context is not None else _default_bound_context
            logger = Logger(namespace, session_id, bound_ctx)
            _loggers[namespace] = logger
            return logger

        # Update session_id/bound context if caller provides them
        if session_id is not None:
            existing.session_id = session_id
        if context is not None:
            existing._bound_context = context

        return existing


def set_default_bound_context(ctx: Any | None) -> None:
    global _default_bound_context
    _default_bound_context = ctx
