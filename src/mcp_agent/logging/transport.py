"""
Transports for the Logger module for MCP Agent, including:
- Local + optional remote event transport
- Async event bus
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Protocol
from pathlib import Path

import aiohttp
from opentelemetry import trace
from rich.json import JSON
from rich.text import Text

from mcp_agent.config import LoggerSettings
from mcp_agent.console import console
from mcp_agent.logging.events import Event, EventFilter
from mcp_agent.logging.json_serializer import JSONSerializer
from mcp_agent.logging.listeners import EventListener, LifecycleAwareListener
from rich import print
import traceback


class EventTransport(Protocol):
    """
    Pluggable interface for sending events to a remote or external system
    (Kafka, RabbitMQ, REST, etc.).
    """

    async def send_event(self, event: Event):
        """
        Send an event to the external system.
        Args:
            event: Event to send.
        """
        ...


class FilteredEventTransport(EventTransport, ABC):
    """
    Event transport that filters events based on a filter before sending.
    """

    def __init__(self, event_filter: EventFilter | None = None):
        self.filter = event_filter

    async def send_event(self, event: Event):
        if not self.filter or self.filter.matches(event):
            await self.send_matched_event(event)

    @abstractmethod
    async def send_matched_event(self, event: Event):
        """Send an event to the external system."""


class NoOpTransport(FilteredEventTransport):
    """Default transport that does nothing (purely local)."""

    async def send_matched_event(self, event):
        """Do nothing."""
        pass


class ConsoleTransport(FilteredEventTransport):
    """Simple transport that prints events to console."""

    def __init__(self, event_filter: EventFilter | None = None):
        super().__init__(event_filter=event_filter)
        # Use shared console instances
        self._serializer = JSONSerializer()
        self.log_level_styles: Dict[str, str] = {
            "info": "bold green",
            "debug": "dim white",
            "warning": "bold yellow",
            "error": "bold red",
        }

    async def send_matched_event(self, event: Event):
        # Map log levels to styles
        style = self.log_level_styles.get(event.type, "white")

        # Use the appropriate console based on event type
        #        output_console = error_console if event.type == "error" else console
        output_console = console

        # Create namespace without None
        namespace = event.namespace
        if event.name:
            namespace = f"{namespace}.{event.name}"

        log_text = Text.assemble(
            (f"[{event.type.upper()}] ", style),
            (f"{event.timestamp.replace(microsecond=0).isoformat()} ", "cyan"),
            (f"{namespace} ", "magenta"),
            (f"- {event.message}", "white"),
        )
        output_console.print(log_text)

        # Print additional data as JSON if available
        if event.data:
            serialized_data = self._serializer(event.data)
            output_console.print(JSON.from_data(serialized_data))


class FileTransport(FilteredEventTransport):
    """Transport that writes events to a file with proper formatting."""

    def __init__(
        self,
        filepath: str | Path,
        event_filter: EventFilter | None = None,
        mode: str = "a",
        encoding: str = "utf-8",
    ):
        """Initialize FileTransport.

        Args:
            filepath: Path to the log file. If relative, the current working directory will be used
            event_filter: Optional filter for events
            mode: File open mode ('a' for append, 'w' for write)
            encoding: File encoding to use
        """
        super().__init__(event_filter=event_filter)
        self.filepath = Path(filepath)
        self.mode = mode
        self.encoding = encoding
        self._serializer = JSONSerializer()

        # Create directory if it doesn't exist
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    async def send_matched_event(self, event: Event) -> None:
        """Write matched event to log file asynchronously.

        Args:
            event: Event to write to file
        """
        # Format the log entry
        namespace = event.namespace
        if event.name:
            namespace = f"{namespace}.{event.name}"

        log_entry = {
            "level": event.type.upper(),
            "timestamp": event.timestamp.isoformat(),
            "namespace": namespace,
            "message": event.message,
        }

        # Add event data if present
        if event.data:
            log_entry["data"] = self._serializer(event.data)

        try:
            with open(self.filepath, mode=self.mode, encoding=self.encoding) as f:
                # Write the log entry as compact JSON (JSONL format)
                f.write(json.dumps(log_entry, separators=(",", ":")) + "\n")
                f.flush()  # Ensure writing to disk
        except IOError as e:
            # Log error without recursion
            print(f"Error writing to log file {self.filepath}: {e}")

    async def close(self) -> None:
        """Clean up resources if needed."""
        pass  # File handles are automatically closed after each write

    @property
    def is_closed(self) -> bool:
        """Check if transport is closed."""
        return False  # Since we open/close per write


class HTTPTransport(FilteredEventTransport):
    """
    Sends events to an HTTP endpoint in batches.
    Useful for sending to remote logging services like Elasticsearch, etc.
    """

    def __init__(
        self,
        endpoint: str,
        headers: Dict[str, str] = None,
        batch_size: int = 100,
        timeout: float = 5.0,
        event_filter: EventFilter | None = None,
    ):
        super().__init__(event_filter=event_filter)
        self.endpoint = endpoint
        self.headers = headers or {}
        self.batch_size = batch_size
        self.timeout = timeout

        self.batch: List[Event] = []
        self.lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._serializer = JSONSerializer()

    async def start(self):
        """Initialize HTTP session."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                headers=self.headers, timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

    async def stop(self):
        """Close HTTP session and flush any remaining events."""
        if self.batch:
            await self._flush()
        if self._session:
            await self._session.close()
            self._session = None

    async def send_matched_event(self, event: Event):
        """Add event to batch, flush if batch is full."""
        async with self.lock:
            self.batch.append(event)
            if len(self.batch) >= self.batch_size:
                await self._flush()

    async def _flush(self):
        """Send batch of events to HTTP endpoint."""
        if not self.batch:
            return

        if not self._session:
            await self.start()

        try:
            # Convert events to JSON-serializable dicts
            events_data = [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.type,
                    "name": event.name,
                    "namespace": event.namespace,
                    "message": event.message,
                    "data": self._serializer(event.data),
                    "trace_id": event.trace_id,
                    "span_id": event.span_id,
                    "context": event.context.dict() if event.context else None,
                }
                for event in self.batch
            ]

            async with self._session.post(self.endpoint, json=events_data) as response:
                if response.status >= 400:
                    text = await response.text()
                    print(
                        f"Error sending log events to {self.endpoint}. "
                        f"Status: {response.status}, Response: {text}"
                    )
        except Exception as e:
            print(f"Error sending log events to {self.endpoint}: {e}")
        finally:
            self.batch.clear()


class AsyncEventBus:
    """
    Async event bus with local in-process listeners + optional remote transport.
    Also injects distributed tracing (trace_id, span_id) if there's a current span.
    """

    _instance = None

    def __init__(self, transport: EventTransport | None = None):
        self.transport: EventTransport = transport or NoOpTransport()
        self.listeners: Dict[str, EventListener] = {}
        self._queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._running = False
        self._stop_event = asyncio.Event()

        # Store the loop we're created on
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    @classmethod
    def get(cls, transport: EventTransport | None = None) -> "AsyncEventBus":
        """Get the singleton instance of the event bus."""
        if cls._instance is None:
            cls._instance = cls(transport=transport)
        elif transport is not None:
            # Update transport if provided
            cls._instance.transport = transport
        return cls._instance

    async def start(self):
        """Start the event bus and all lifecycle-aware listeners."""
        if self._running:
            return

        # Start each lifecycle-aware listener
        for listener in self.listeners.values():
            if isinstance(listener, LifecycleAwareListener):
                await listener.start()

        # Clear stop event and start processing
        self._stop_event.clear()
        self._running = True
        self._task = asyncio.create_task(self._process_events())

    async def stop(self):
        """Stop the event bus and all lifecycle-aware listeners."""
        if not self._running:
            return

        # Signal processing to stop
        self._running = False
        self._stop_event.set()

        # Try to process remaining items with a timeout
        if not self._queue.empty():
            try:
                # Give some time for remaining items to be processed
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                # If we timeout, drain the queue to prevent deadlock
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                        self._queue.task_done()
                    except asyncio.QueueEmpty:
                        break
            except Exception as e:
                print(f"Error during queue cleanup: {e}")

        # Cancel and wait for task with timeout
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                # Wait for task to complete with timeout
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass  # Task was cancelled or timed out
            except Exception as e:
                print(f"Error cancelling process task: {e}")
            finally:
                self._task = None

        # Stop each lifecycle-aware listener
        for listener in self.listeners.values():
            if isinstance(listener, LifecycleAwareListener):
                try:
                    await asyncio.wait_for(listener.stop(), timeout=3.0)
                except asyncio.TimeoutError:
                    print(f"Timeout stopping listener: {listener}")
                except Exception as e:
                    print(f"Error stopping listener: {e}")

    async def emit(self, event: Event):
        """Emit an event to all listeners and transport."""
        # Inject current tracing info if available
        span = trace.get_current_span()
        if span.is_recording():
            ctx = span.get_span_context()
            event.trace_id = f"{ctx.trace_id:032x}"
            event.span_id = f"{ctx.span_id:016x}"

        # Forward to transport first (immediate processing)
        try:
            await self.transport.send_event(event)
        except Exception as e:
            print(f"Error in transport.send_event: {e}")

        # Then queue for listeners
        await self._queue.put(event)

    def add_listener(self, name: str, listener: EventListener):
        """Add a listener to the event bus."""
        self.listeners[name] = listener

    def remove_listener(self, name: str):
        """Remove a listener from the event bus."""
        self.listeners.pop(name, None)

    async def _process_events(self):
        """Process events from the queue until stopped."""
        while self._running:
            try:
                # Use wait_for with a timeout to allow checking running state
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                # Process the event through all listeners
                tasks = []
                for listener in self.listeners.values():
                    try:
                        tasks.append(listener.handle_event(event))
                    except Exception as e:
                        print(f"Error creating listener task: {e}")

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            print(f"Error in listener: {r}")
                            print(
                                f"Stacktrace: {''.join(traceback.format_exception(type(r), r, r.__traceback__))}"
                            )

                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in event processing loop: {e}")
                continue

        # Process remaining events in queue
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                tasks = []
                for listener in self.listeners.values():
                    try:
                        tasks.append(listener.handle_event(event))
                    except Exception:
                        pass
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break


def create_transport(
    settings: LoggerSettings, event_filter: EventFilter | None = None
) -> EventTransport:
    """Create event transport based on settings."""
    if settings.type == "none":
        return NoOpTransport(event_filter=event_filter)
    elif settings.type == "console":
        return ConsoleTransport(event_filter=event_filter)
    elif settings.type == "file":
        if not settings.path:
            raise ValueError("File path required for file transport")
        return FileTransport(
            filepath=settings.path,
            event_filter=event_filter,
        )
    elif settings.type == "http":
        if not settings.http_endpoint:
            raise ValueError("HTTP endpoint required for HTTP transport")
        return HTTPTransport(
            endpoint=settings.http_endpoint,
            headers=settings.http_headers,
            batch_size=settings.batch_size,
            timeout=settings.http_timeout,
            event_filter=event_filter,
        )
    else:
        raise ValueError(f"Unsupported transport type: {settings.type}")
