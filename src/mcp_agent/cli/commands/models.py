"""
Models command group: list and set-default (scaffold).
"""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mcp_agent.workflows.llm.llm_selector import load_default_models


app = typer.Typer(help="List and manage models")
console = Console()


@app.command("list")
def list_models(format: str = typer.Option("text", "--format")) -> None:
    """List known model catalog (from embedded benchmarks)."""
    models = load_default_models()
    if format.lower() == "json":
        data = [m.model_dump() for m in models]
        console.print_json(json.dumps(data))
        return
    if format.lower() == "yaml":
        try:
            import yaml  # type: ignore

            console.print(yaml.safe_dump([m.model_dump() for m in models], sort_keys=False))
            return
        except Exception:
            pass

    table = Table(show_header=True, header_style="bold", title="Models")
    table.add_column("Provider")
    table.add_column("Name")
    table.add_column("Context")
    table.add_column("Tool use")
    for m in models:
        table.add_row(m.provider, m.name, str(m.context_window or ""), "✔" if m.tool_calling else "")
    console.print(table)


@app.command("set-default")
def set_default(name: str = typer.Argument(..., help="Provider-qualified name")) -> None:
    """Scaffold for setting default model (to be implemented)."""
    # Full implementation will update config.yaml; for now just acknowledge.
    console.print(f"Setting default model to: {name} (scaffold)")


