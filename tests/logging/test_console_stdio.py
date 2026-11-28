"""Console diagnostics must not write to stdout (MCP stdio reserves it)."""

from __future__ import annotations

import io
import sys
from datetime import datetime

import pytest

from mcp_agent.console import (
    console,
    error_console,
    log_console,
    redirect_console_output_to_stderr,
    server_console,
)
from mcp_agent.logging.events import Event
import mcp_agent.logging.logger  # noqa: F401  # import logger first to avoid circular import
from mcp_agent.logging.transport import ConsoleTransport


@pytest.fixture
def restore_console_files():
    originals = {
        "console": console.file,
        "error_console": error_console.file,
        "log_console": log_console.file,
        "server_console": server_console.file,
    }
    try:
        yield
    finally:
        console.file = originals["console"]
        error_console.file = originals["error_console"]
        log_console.file = originals["log_console"]
        server_console.file = originals["server_console"]


@pytest.mark.anyio
async def test_console_transport_writes_to_stderr_not_stdout(
    restore_console_files,
) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    log_console.file = stderr
    # If the transport still targeted the shared stdout console, this would catch it.
    console.file = stdout

    transport = ConsoleTransport()
    await transport.send_matched_event(
        Event(
            type="info",
            namespace="mcp_agent.test",
            message="startup diagnostic",
            timestamp=datetime(2026, 11, 28, 12, 0, 0),
        )
    )

    err = stderr.getvalue()
    assert "startup diagnostic" in err
    assert "[INFO]" in err
    assert stdout.getvalue() == ""


def test_redirect_console_output_to_stderr_points_shared_consoles_at_stderr(
    restore_console_files,
) -> None:
    redirect_console_output_to_stderr()
    assert console.file is sys.stderr
    assert error_console.file is sys.stderr
    assert log_console.file is sys.stderr
    assert server_console.file is sys.stderr
