"""
Doctor: diagnostics (scaffold).
"""

from __future__ import annotations

import platform
import sys

import typer
from rich.console import Console
from rich.table import Table


app = typer.Typer(help="Comprehensive diagnostics")
console = Console()


@app.callback(invoke_without_command=True)
def doctor() -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("OS", platform.platform())
    table.add_row("Python", sys.version.split(" ")[0])
    console.print(table)


