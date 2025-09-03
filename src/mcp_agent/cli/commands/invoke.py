"""
Invoke an agent or workflow programmatically (scaffold).
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console

from mcp_agent.app import MCPApp


app = typer.Typer(help="Invoke an agent or workflow programmatically")
console = Console()


@app.callback(invoke_without_command=True)
def invoke(
    agent: Optional[str] = typer.Option(None, "--agent"),
    workflow: Optional[str] = typer.Option(None, "--workflow"),
    message: Optional[str] = typer.Option(None, "--message", "-m"),
    vars: Optional[str] = typer.Option(None, "--vars", help="JSON structured inputs"),
    script: Optional[str] = typer.Option(None, "--script"),
    model: Optional[str] = typer.Option(None, "--model"),
) -> None:
    """Minimal execution placeholder; resolves and prints inputs."""
    try:
        payload = json.loads(vars) if vars else None
    except Exception as e:
        typer.secho(f"Invalid --vars JSON: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(6)

    async def _run():
        app = MCPApp(name="mcp-agent invoke")
        async with app.run():
            console.print({
                "agent": agent,
                "workflow": workflow,
                "message": message,
                "vars": payload,
                "script": script,
                "model": model,
            })

    asyncio.run(_run())


