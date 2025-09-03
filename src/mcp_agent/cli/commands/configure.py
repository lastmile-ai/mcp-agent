"""
Client integration helpers (scaffold).
"""

from __future__ import annotations

import typer
from rich.console import Console


app = typer.Typer(help="Client integration helpers")
console = Console()


@app.callback(invoke_without_command=True)
def configure(
    server_url: str = typer.Argument(...),
    client: str = typer.Option(..., "--client", help="cursor|claude|vscode|..."),
    write: bool = typer.Option(False, "--write"),
    open: bool = typer.Option(False, "--open"),
    format: str = typer.Option("text", "--format"),
) -> None:
    console.print({
        "server_url": server_url,
        "client": client,
        "write": write,
        "open": open,
        "format": format,
    })


