"""
Build preflight (scaffold).
"""

from __future__ import annotations

import typer
from rich.console import Console


app = typer.Typer(help="Preflight and bundle prep for deployment")
console = Console()


@app.callback(invoke_without_command=True)
def build(check_only: bool = typer.Option(False, "--check-only")) -> None:
    console.print(f"Build preflight (check_only={check_only}) - scaffold")


