"""
Quickstart examples: scaffolded adapters over repository examples.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table


app = typer.Typer(help="Copy curated examples")
console = Console()


EXAMPLE_ROOT = Path(__file__).parents[4] / "examples"


def _copy_tree(src: Path, dst: Path, force: bool) -> int:
    if not src.exists():
        typer.echo(f"Source not found: {src}", err=True)
        return 0
    if dst.exists() and force:
        shutil.rmtree(dst)
    if not dst.exists():
        shutil.copytree(src, dst)
        return 1
    return 0


@app.callback(invoke_without_command=True)
def overview() -> None:
    table = Table(title="Quickstarts")
    table.add_column("Name")
    table.add_column("Path")
    rows = [
        ("workflow", "examples/workflows"),
        ("researcher", "examples/usecases/mcp_researcher"),
        ("data-analysis", "examples/usecases/mcp_financial_analyzer"),
        ("state-transfer", "examples/workflows/workflow_router"),
    ]
    for n, p in rows:
        table.add_row(n, p)
    console.print(table)


@app.command()
def workflow(dir: Path = typer.Argument(Path(".")), force: bool = typer.Option(False, "--force", "-f")) -> None:
    src = EXAMPLE_ROOT / "workflows"
    dst = dir.resolve() / "workflow"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


