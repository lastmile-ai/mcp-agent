"""
Listeners for the logger module of MCP Agent.
"""

import asyncio
import logging
import time

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from mcp_agent.logging.events import Event, EventFilter, EventType
from mcp_agent.logging.event_progress import convert_log_event

if TYPE_CHECKING:  # pragma: no cover - for type checking only
    from mcp.types import LoggingLevel


class UpstreamServerSessionProtocol(Protocol):
    async def send_log_message(
        self,
        level: "LoggingLevel",
        data: Dict[str, Any],
        logger: str | None = None,
        related_request_id: str | None = None,
    ) -> None: ...


class EventListener(ABC):
    """Base async listener that processes events."""

    @abstractmethod
    async def handle_event(self, event: Event):
        """Process an incoming event."""


class LifecycleAwareListener(EventListener):
    """
    Optionally override start()/stop() for setup/teardown.
    The event bus calls these at bus start/stop time.
    """

    async def start(self):
        """Start an event listener, usually when the event bus is set up."""
        pass

    async def stop(self):
        """Stop an event listener, usually when the event bus is shutting down."""
        pass


class FilteredListener(LifecycleAwareListener):
    """
    Only processes events that pass the given filter.
    Subclasses override _handle_matched_event().
    """

    def __init__(self, event_filter: EventFilter | None = None):
        """
        Initialize the listener.
        Args:
            filter: Event filter to apply to incoming events.
        """
        self.filter = event_filter

    async def handle_event(self, event):
        if not self.filter or self.filter.matches(event):
            await self.handle_matched_event(event)

    async def handle_matched_event(self, event: Event):
        """Process an event that matches the filter."""
        pass


class LoggingListener(FilteredListener):
    """
    Routes events to Python's logging facility with appropriate severity level.
    """

    def __init__(
        self,
        event_filter: EventFilter | None = None,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize the listener.
        Args:
            logger: Logger to use for event processing. Defaults to 'mcp_agent'.
        """
        super().__init__(event_filter=event_filter)
        self.logger = logger or logging.getLogger("mcp_agent")

    async def handle_matched_event(self, event):
        level_map: Dict[EventType, int] = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        level = level_map.get(event.type, logging.INFO)

        # Check if this is a server stderr message and format accordingly
        if event.name == "mcpserver.stderr":
            message = f"MCP Server: {event.message}"
        else:
            message = event.message

        self.logger.log(
            level,
            "[%s] %s",
            event.namespace,
            message,
            extra={
                "event_data": event.data,
                "span_id": event.span_id,
                "trace_id": event.trace_id,
                "event_name": event.name,
            },
        )


class ProgressListener(LifecycleAwareListener):
    """
    Listens for all events pre-filtering and converts them to progress events
    for display. By inheriting directly from LifecycleAwareListener instead of
    FilteredListener, we get events before any filtering occurs.
    """

    def __init__(self, display=None, token_counter=None):
        """Initialize the progress listener.
        Args:
            display: Optional display handler. If None, the shared progress_display will be used if available.
        """
        self.display = display
        if self.display is None:
            from mcp_agent.logging.progress_display import create_progress_display

            self.display = create_progress_display(token_counter=token_counter)

    async def start(self):
        """Start the progress display."""
        if self.display:
            self.display.start()

    async def stop(self):
        """Stop the progress display."""
        if self.display:
            self.display.stop()

    async def handle_event(self, event: Event):
        """Process an incoming event and display progress if relevant."""
        if self.display and event.data:
            progress_event = convert_log_event(event)
            if progress_event:
                self.display.update(progress_event)


class BatchingListener(FilteredListener):
    """
    Accumulates events in memory, flushes them in batches.
    Here we just print the batch size, but you might store or forward them.
    """

    def __init__(
        self,
        event_filter: EventFilter | None = None,
        batch_size: int = 5,
        flush_interval: float = 2.0,
    ):
        """
        Initialize the listener.
        Args:
            batch_size: Number of events to accumulate before flushing.
            flush_interval: Time in seconds to wait before flushing events.
        """
        super().__init__(event_filter=event_filter)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.batch: List[Event] = []
        self.last_flush: float = time.time()  # Time of last flush
        self._flush_task: asyncio.Task | None = None  # Task for periodic flush loop
        self._stop_event = None  # Event to signal flush task to stop

    async def start(self, loop=None):
        """Spawn a periodic flush loop."""
        self._stop_event = asyncio.Event()
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self):
        """Stop flush loop and flush any remaining events."""
        if self._stop_event:
            self._stop_event.set()

        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush()

    async def _periodic_flush(self):
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.flush_interval
                    )
                except asyncio.TimeoutError:
                    await self.flush()
        except asyncio.CancelledError:
            pass
        finally:
            await self.flush()  # Final flush

    async def handle_matched_event(self, event):
        self.batch.append(event)
        if len(self.batch) >= self.batch_size:
            await self.flush()

    async def flush(self):
        """Flush the current batch of events."""
        if not self.batch:
            return
        to_process = self.batch[:]
        self.batch.clear()
        self.last_flush = time.time()
        await self._process_batch(to_process)

    async def _process_batch(self, events: List[Event]):
        pass


class MCPUpstreamLoggingListener(FilteredListener):
    """
    Sends matched log events to the connected MCP client via the upstream_session
    carried on each Event (runtime-only field). If no upstream_session is present,
    the event is skipped.
    """

    def __init__(self, event_filter: EventFilter | None = None) -> None:
        super().__init__(event_filter=event_filter)

    async def handle_matched_event(self, event: Event) -> None:
        # Use upstream session provided on the event
        upstream_session: Optional[UpstreamServerSessionProtocol] = getattr(
            event, "upstream_session", None
        )

        if upstream_session is None:
            # No upstream_session available; silently skip
            return

        # Map our EventType to MCP LoggingLevel; fold progress -> info
        mcp_level_map: Dict[str, str] = {
            "debug": "debug",
            "info": "info",
            "warning": "warning",
            "error": "error",
            "progress": "info",
        }
        # Use string type to avoid hard dependency; annotated for type checkers
        mcp_level: "LoggingLevel" = mcp_level_map.get(event.type, "info")  # type: ignore[assignment]

        # Build structured data payload
        data: Dict[str, Any] = {
            "message": event.message,
            "namespace": event.namespace,
            "name": event.name,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.data:
            # Merge user-provided event data under 'data'
            data["data"] = event.data
        if event.trace_id or event.span_id:
            data["trace"] = {"trace_id": event.trace_id, "span_id": event.span_id}
        if event.context is not None:
            try:
                data["context"] = event.context.dict()
            except Exception:
                pass

        # Determine logger name (namespace + optional name)
        logger_name: str = (
            event.namespace if not event.name else f"{event.namespace}.{event.name}"
        )

        try:
            await upstream_session.send_log_message(
                level=mcp_level,  # type: ignore[arg-type]
                data=data,
                logger=logger_name,
            )
        except Exception as e:
            # Avoid raising inside listener; best-effort delivery
            _ = e
