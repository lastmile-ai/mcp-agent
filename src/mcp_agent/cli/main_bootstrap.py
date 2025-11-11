"""
Bootstrap wrapper that shows a Rich spinner while the main CLI wiring imports.
Keeps heavy imports out of import time so tests and other tools stay quiet.
"""

from __future__ import annotations
from rich.console import Console

# Adding a loader indicator and starting it here since importing takes some time


def run() -> None:
    """Display a spinner during CLI bootstrap, then hand off to main.run()."""
    console = Console(stderr=True)
    with console.status("[dim]Loading mcp-agent CLI...[/dim]", spinner="dots"):
        from mcp_agent.cli.main import run as main_run  # heavy imports happen here
    main_run()
