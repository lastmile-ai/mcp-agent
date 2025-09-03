"""
Local server helpers: add/import/list/test (initial scaffolding for add/list/test).
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mcp_agent.config import Settings, MCPServerSettings, MCPSettings


app = typer.Typer(help="Local server helpers")
console = Console()


@app.command("list")
def list_servers() -> None:
    settings = Settings()
    servers = (settings.mcp.servers if settings.mcp else {}) or {}
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Transport")
    table.add_column("URL/Command")
    for name, s in servers.items():
        target = s.url or s.command or ""
        table.add_row(name, s.transport, target)
    console.print(table)


@app.command("add")
def add(
    kind: str = typer.Argument(..., help="http|sse|stdio|npx|uvx"),
    value: str = typer.Argument(..., help="url or quoted command"),
    name: Optional[str] = typer.Option(None, "--name"),
    auth: Optional[str] = typer.Option(None, "--auth"),
) -> None:
    settings = Settings()
    if settings.mcp is None:
        settings.mcp = MCPSettings()
    servers = settings.mcp.servers
    entry = MCPServerSettings()
    if kind in ("http", "sse"):
        entry.transport = kind
        entry.url = value
        if auth:
            entry.headers = {"Authorization": f"Bearer {auth}"}
    else:
        entry.transport = "stdio"
        # naive split; robust parsing can be added later
        parts = value.split()
        entry.command = parts[0]
        entry.args = parts[1:]
    srv_name = name or (value.split("/")[-1] if kind in ("http", "sse") else parts[0])
    servers[srv_name] = entry
    console.print(f"Added server '{srv_name}' (not yet persisted)")


@app.command("test")
def test(name: str, timeout: float = typer.Option(10.0, "--timeout")) -> None:
    """Scaffold for server health probe: lists tools if reachable (future)."""
    console.print(f"Testing server {name} (timeout={timeout}) - scaffold")


