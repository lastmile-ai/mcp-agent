"""
Utilities for working with stdio-based MCP transports.

In MCP 1.19 the stdio client started forwarding JSON parsing errors from the
server's stdout stream as exceptions on the transport. Many MCP servers still
emit setup logs on stdout (e.g. package managers), which now surface as noisy
tracebacks for every log line. This module wraps the upstream stdio transport
and filters out clearly non-JSON stdout lines so that normal logging output
does not bubble up as transport errors.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Iterable

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import ValidationError

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.message import SessionMessage

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)

# JSON-RPC messages should always be JSON objects, but we keep literal checks
# to stay conservative if upstream ever sends arrays or literals.
_LITERAL_PREFIXES: tuple[str, ...] = ("true", "false", "null")
_MESSAGE_START_CHARS = {"{", "["}


def _should_ignore_exception(exc: Exception) -> bool:
    """
    Returns True when the exception represents a non-JSON stdout line that we can
    safely drop.
    """
    if not isinstance(exc, ValidationError):
        return False

    errors: Iterable[dict] = exc.errors()
    first = next(iter(errors), None)
    if not first or first.get("type") != "json_invalid":
        return False

    input_value = first.get("input")
    if not isinstance(input_value, str):
        return False

    stripped = input_value.strip()
    if not stripped:
        return True

    first_char = stripped[0]
    lowered = stripped.lower()
    if first_char in _MESSAGE_START_CHARS or any(
        lowered.startswith(prefix) for prefix in _LITERAL_PREFIXES
    ):
        # Likely a legitimate JSON payload; don't swallow
        return False

    return True


def _truncate(value: str, length: int = 120) -> str:
    """
    Truncate long log lines so debug output remains readable.
    """
    if len(value) <= length:
        return value
    return value[: length - 3] + "..."


@asynccontextmanager
async def filtered_stdio_client(
    server_name: str, server: StdioServerParameters
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
    ],
    None,
]:
    """
    Wrap the upstream stdio_client so obviously non-JSON stdout lines are filtered.
    """
    async with stdio_client(server=server) as (read_stream, write_stream):
        filtered_send, filtered_recv = anyio.create_memory_object_stream[
            SessionMessage | Exception
        ](0)

        async def _forward_stdout() -> None:
            try:
                async with read_stream:
                    async for item in read_stream:
                        if isinstance(item, Exception) and _should_ignore_exception(
                            item
                        ):
                            try:
                                errors = item.errors()  # type: ignore[attr-defined]
                                offending = errors[0].get("input", "") if errors else ""
                            except Exception:
                                offending = ""
                            if offending:
                                logger.debug(
                                    "%s: ignoring non-JSON stdout: %s",
                                    server_name,
                                    _truncate(str(offending)),
                                )
                            else:
                                logger.debug(
                                    "%s: ignoring non-JSON stdout (unable to capture)",
                                    server_name,
                                )
                            continue

                        try:
                            await filtered_send.send(item)
                        except anyio.ClosedResourceError:
                            break
            except anyio.ClosedResourceError:
                # Consumer closed; nothing else to forward
                pass
            finally:
                await filtered_send.aclose()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_forward_stdout)
            try:
                yield filtered_recv, write_stream
            finally:
                tg.cancel_scope.cancel()
