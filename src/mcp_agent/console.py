"""
Centralized console configuration for MCP Agent.

This module provides shared console instances for consistent output handling:
- console: Main console for general output
- error_console: Error console for application errors (writes to stderr)
- log_console: Diagnostic logger console (writes to stderr)
- server_console: Special console for MCP server output
"""

import sys

from rich.console import Console

# Main console for general output
console = Console(
    color_system="auto",
)

# Error console for application errors
error_console = Console(
    stderr=True,
    style="bold red",
)

# Logger / diagnostic console. Writes to stderr so MCP stdio transports can
# keep stdout reserved for JSON-RPC messages.
log_console = Console(
    stderr=True,
    color_system="auto",
)

# Special console for MCP server output
# This could have custom styling to distinguish server messages
server_console = Console(
    # Not stderr since we want to maintain output ordering with other messages
    style="dim blue",  # Or whatever style makes server output distinct
)


def redirect_console_output_to_stderr() -> None:
    """Point shared consoles at stderr.

    The MCP stdio transport reserves stdout for protocol messages. Call this
    before initializing an app that will be served over stdio so progress
    displays, elicitation prompts, and other shared-console output do not land
    on the MCP stream.
    """
    for shared in (console, error_console, log_console, server_console):
        shared.file = sys.stderr
