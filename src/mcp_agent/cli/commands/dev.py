"""
Run app locally with (future) live reload and diagnostics (scaffold).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from mcp_agent.app import MCPApp


app = typer.Typer(help="Run app locally with diagnostics")
console = Console()


@app.callback(invoke_without_command=True)
def dev(script: Path = typer.Option(Path("agent.py"), "--script")) -> None:
    """Start the user's app from a script (basic run)."""

    async def _run():
        # For now, just initialize an empty MCPApp; later we will import the script
        mcp_app = MCPApp(name="mcp-agent dev")
        async with mcp_app.run():
            console.print(f"Running {script} (scaffold)")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


