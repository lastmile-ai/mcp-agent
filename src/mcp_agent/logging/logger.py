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

    def __init__(self, namespace: str):
        self.namespace = namespace
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
        if loop.is_running():
            # If we're in a thread with a running loop, schedule the coroutine
            asyncio.create_task(self.event_bus.emit(event))
        else:
            # If no loop is running, run it until the emit completes
            loop.run_until_complete(self.event_bus.emit(event))

    def event(
        self,
        etype: EventType,
        ename: str | None,
        message: str,
        context: EventContext | None,
        data: dict,
    ):
        """Create and emit an event."""
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
            bus.add_listener("progress", ProgressListener())

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


def get_logger(namespace: str) -> Logger:
    """
    Get a logger instance for a given namespace.
    Creates a new logger if one doesn't exist for this namespace.

    Args:
        namespace: The namespace for the logger (e.g. "agent.helper", "workflow.demo")

    Returns:
        A Logger instance for the given namespace
    """

    with _logger_lock:
        if namespace not in _loggers:
            _loggers[namespace] = Logger(namespace)
        return _loggers[namespace]


##########
# Example
##########


# class Agent:
#     """Shows how to combine Logger with OTel's @telemetry.traced decorator."""

#     def __init__(self, name: str):
#         self.logger = Logger(f"agent.{name}")

#     @telemetry.traced("agent.call_tool", kind=SpanKind.CLIENT)
#     async def call_tool(self, tool_name: str, **kwargs):
#         await self.logger.info(
#             f"Calling tool '{tool_name}'", name="TOOL_CALL_START", **kwargs
#         )
#         await asyncio.sleep(random.uniform(0.1, 0.3))
#         # Possibly do real logic here
#         await self.logger.debug(
#             f"Completed tool call '{tool_name}'", name="TOOL_CALL_END"
#         )


# class Workflow:
#     """Example workflow that logs multiple steps, also with optional tracing."""

#     def __init__(self, name: str, steps: List[str]):
#         self.logger = Logger(f"workflow.{name}")
#         self.steps = steps

#     @telemetry.traced("workflow.run", kind=SpanKind.INTERNAL)
#     async def run(self):
#         await self.logger.info(
#             "Workflow started", name="WORKFLOW_START", steps=len(self.steps)
#         )
#         for i, step_name in enumerate(self.steps, start=1):
#             pct = round((i / len(self.steps)) * 100, 2)
#             await self.logger.progress(
#                 f"Executing {step_name}", name="WORKFLOW_STEP", percentage=pct
#             )
#             await asyncio.sleep(random.uniform(0.1, 0.3))
#             await self.logger.milestone(
#                 f"Completed {step_name}", name="WORKFLOW_MILESTONE", step_index=i
#             )
#         await self.logger.status("Workflow complete", name="WORKFLOW_DONE")


# ###############################################################################
# # 10) Demo Main
# ###############################################################################


# async def main():
#     # 1) Configure Python logging
#     logging.basicConfig(level=logging.INFO)

#     # 2) Get the event bus and add local listeners
#     bus = AsyncEventBus.get()
#     bus.add_listener("logging", LoggingListener())
#     bus.add_listener("batching", BatchingListener(batch_size=3, flush_interval=2.0))

#     # 3) Optionally set up distributed transport
#     # configure_distributed("https://my-remote-logger.example.com")

#     # 4) Start the event bus
#     await bus.start()

#     # 5) Run example tasks
#     agent = Agent("assistant")
#     workflow = Workflow("demo_flow", ["init", "process", "cleanup"])

#     agent_task = asyncio.create_task(agent.call_tool("my-tool", foo="bar"))
#     workflow_task = asyncio.create_task(workflow.run())

#     # Also demonstrate timed context manager
#     logger = Logger("misc")
#     with event_context(
#         logger, "SynchronousBlock", event_type="info", name="SYNCHRONOUS_BLOCK"
#     ):
#         time.sleep(0.5)  # do a blocking operation

#     # Wait for tasks
#     await asyncio.gather(agent_task, workflow_task)

#     # 6) Stop the bus (flush & close)
#     await bus.stop()


# if __name__ == "__main__":
#     asyncio.run(main())
