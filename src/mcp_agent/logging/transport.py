"""
Transports for the Logger module for MCP Agent, including:
- Local + optional remote event transport
- Async event bus
"""

import asyncio
import json
import uuid
import datetime
import sys
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

        # Batching for efficient writes
        self._write_buffer: List[str] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._running = True

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

        # Prepare the log line
        log_line = json.dumps(log_entry, separators=(",", ":")) + "\n"

        # Use asyncio to run file I/O in executor to avoid blocking
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Use default executor
                self._write_to_file,
                log_line,
            )
        except IOError as e:
            # Log error without recursion
            print(f"Error writing to log file {self.filepath}: {e}")

    def _write_to_file(self, log_line: str) -> None:
        """Synchronous file write helper for use in executor."""
        with open(self.filepath, mode=self.mode, encoding=self.encoding) as f:
            f.write(log_line)
            f.flush()  # Ensure writing to disk

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
        self._task: asyncio.Task | None = None
        self._running = False

    def init_queue(self):
        if self._running:
            return
        self._queue = asyncio.Queue()
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

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance.
        This is primarily useful for testing scenarios where you need to ensure
        a clean state between tests.
        """
        if cls._instance:
            # Signal shutdown
            cls._instance._running = False
            if hasattr(cls._instance, "_stop_event"):
                try:
                    # _stop_event.set() schedules on the event's loop; this can fail if
                    # the loop is already closed in test teardown. Swallow to ensure
                    # reset never raises in those cases.
                    cls._instance._stop_event.set()
                except RuntimeError:
                    pass
                except Exception:
                    pass

            # Clear the singleton instance
            cls._instance = None

    async def start(self):
        """Start the event bus and all lifecycle-aware listeners."""
        # Always ensure queue is initialized
        if not hasattr(self, "_queue"):
            self.init_queue()

        # Start each lifecycle-aware listener (even if already running)
        # This ensures listeners are started even if auto-start happened
        for listener in self.listeners.values():
            if isinstance(listener, LifecycleAwareListener):
                await listener.start()

        # If not already running, start the event processing task
        if not self._running:
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
        if hasattr(self, "_stop_event"):
            self._stop_event.set()

        # Try to process remaining items with a timeout if queue exists
        if hasattr(self, "_queue") and not self._queue.empty():
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

        # Initialize queue and start processing if needed
        if not hasattr(self, "_queue"):
            self.init_queue()
            # Auto-start the event processing task if not running
            if not self._running:
                self._running = True
                self._task = asyncio.create_task(self._process_events())

        # Then queue for listeners
        await self._queue.put(event)

    def emit_with_stderr_transport(self, event: Event):
        print(
            f"[{event.type}] {event.namespace}: {event.message}",
            file=sys.stderr,
        )

        # Initialize queue and start processing if needed
        if not hasattr(self, "_queue"):
            self.init_queue()
            # Auto-start the event processing task if not running
            if not self._running:
                self._running = True
                self._task = asyncio.create_task(self._process_events())

        self._queue.put_nowait(event)

    async def _send_to_transport(self, event: Event):
        """Send event to transport with error handling."""
        try:
            await self.transport.send_event(event)
        except Exception as e:
            print(f"Error in transport.send_event: {e}")

    def add_listener(self, name: str, listener: EventListener):
        """Add a listener to the event bus."""
        self.listeners[name] = listener

    def remove_listener(self, name: str):
        """Remove a listener from the event bus."""
        self.listeners.pop(name, None)

    async def _process_events(self):
        """Process events from the queue until stopped."""
        while self._running:
            event = None
            try:
                # Use wait with both queue.get() and stop_event.wait() to avoid timeout delays
                try:
                    # Check if we should be stopping first
                    if not self._running or self._stop_event.is_set():
                        break

                    # Wait for either an event or stop signal without timeout
                    queue_task = asyncio.create_task(self._queue.get())
                    stop_task = asyncio.create_task(self._stop_event.wait())

                    done, pending = await asyncio.wait(
                        [queue_task, stop_task], return_when=asyncio.FIRST_COMPLETED
                    )

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    # Check which task completed
                    if stop_task in done:
                        break

                    if queue_task in done:
                        event = queue_task.result()
                    else:
                        continue
                except asyncio.CancelledError:
                    break

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

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in event processing loop: {e}")
                continue
            finally:
                # Always mark the task as done if we got an event
                if event is not None:
                    self._queue.task_done()

        # Process remaining events in queue if it exists
        if hasattr(self, "_queue"):
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


class MultiTransport(EventTransport):
    """Transport that sends events to multiple configured transports."""

    def __init__(self, transports: List[EventTransport]):
        """Initialize MultiTransport with a list of transports.

        Args:
            transports: List of EventTransport instances to use
        """
        self.transports = transports

    async def send_event(self, event: Event):
        """Send event to all configured transports in parallel.

        Args:
            event: Event to send
        """

        # helper function to handle exceptions
        async def send_with_exception_handling(transport):
            try:
                await transport.send_event(event)
                return None
            except Exception as e:
                return (transport, e)

        results = await asyncio.gather(
            *[send_with_exception_handling(transport) for transport in self.transports],
            return_exceptions=False,
        )

        exceptions = [result for result in results if result is not None]
        if exceptions:
            print(f"Errors occurred in {len(exceptions)} transports:")
            for transport, exc in exceptions:
                print(f"  {transport.__class__.__name__}: {exc}")


def get_log_filename(settings: LoggerSettings, session_id: str | None = None) -> str:
    """Generate a log filename based on the configuration.

    Args:
        settings: Logger settings containing path configuration
        session_id: Optional session ID to use in the filename

    Returns:
        String path for the log file
    """
    # If we have a standard path setting and no advanced path settings, use the standard path
    if settings.path and not settings.path_settings:
        return settings.path

    # If we have advanced path settings, use those
    if settings.path_settings:
        path_pattern = settings.path_settings.path_pattern
        unique_id_type = settings.path_settings.unique_id

        # Only use session_id when explicitly configured as "session_id"
        if unique_id_type == "session_id":
            # Use provided session_id if available, otherwise generate a new UUID
            unique_id = session_id if session_id else str(uuid.uuid4())
        else:  # For any other setting (including "timestamp"), use the original behavior
            now = datetime.datetime.now()
            time_format = settings.path_settings.timestamp_format
            unique_id = now.strftime(time_format)

        return path_pattern.replace("{unique_id}", unique_id)

    raise ValueError("No path settings provided")


def create_transport(
    settings: LoggerSettings,
    event_filter: EventFilter | None = None,
    session_id: str | None = None,
) -> EventTransport:
    """Create event transport based on settings."""
    transports: List[EventTransport] = []
    transport_types = []

    # Determine which transport types to use (from new or legacy config)
    if hasattr(settings, "transports") and settings.transports:
        transport_types = settings.transports
    else:
        transport_types = [settings.type]

    for transport_type in transport_types:
        if transport_type == "none":
            continue
        elif transport_type == "console":
            transports.append(ConsoleTransport(event_filter=event_filter))
        elif transport_type == "file":
            filepath = get_log_filename(settings, session_id)
            if not filepath:
                raise ValueError(
                    "File path required for file transport. Either specify 'path' or configure 'path_settings'"
                )

            transports.append(
                FileTransport(filepath=filepath, event_filter=event_filter)
            )
        elif transport_type == "http":
            if not settings.http_endpoint:
                raise ValueError("HTTP endpoint required for HTTP transport")

            transports.append(
                HTTPTransport(
                    endpoint=settings.http_endpoint,
                    headers=settings.http_headers,
                    batch_size=settings.batch_size,
                    timeout=settings.http_timeout,
                    event_filter=event_filter,
                )
            )
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")

    if not transports:
        return NoOpTransport(event_filter=event_filter)
    elif len(transports) == 1:
        return transports[0]
    else:
        return MultiTransport(transports)
