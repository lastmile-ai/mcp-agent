"""
Ephemeral REPL for quick iteration (scaffold).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from mcp_agent.app import MCPApp


app = typer.Typer(help="Ephemeral REPL for quick iteration")
console = Console()


@app.callback(invoke_without_command=True)
def chat(
    name: Optional[str] = typer.Option(None, "--name"),
    model: Optional[str] = typer.Option(None, "--model"),
    message: Optional[str] = typer.Option(None, "--message", "-m"),
) -> None:
    """Minimal placeholder: starts MCPApp and exits; full REPL later."""

    async def _run():
        app = MCPApp(name=name or "mcp-agent chat")
        async with app.run():
            if message:
                # Placeholder: no LLM wired yet
                console.print(message)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


