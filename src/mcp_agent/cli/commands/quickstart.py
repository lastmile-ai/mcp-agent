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
def workflow(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    src = EXAMPLE_ROOT / "workflows"
    dst = dir.resolve() / "workflow"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command()
def researcher(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    src = EXAMPLE_ROOT / "usecases" / "mcp_researcher"
    dst = dir.resolve() / "researcher"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("elicitations")
def elicitations_qs(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    src = EXAMPLE_ROOT.parent / "mcp" / "elicitations"
    dst = dir.resolve() / "elicitations"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("state-transfer")
def state_transfer(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    src = EXAMPLE_ROOT / "workflows" / "workflow_router"
    dst = dir.resolve() / "state-transfer"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("data-analysis")
def data_analysis(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    # Map to financial analyzer example as the closest match
    src = EXAMPLE_ROOT / "usecases" / "mcp_financial_analyzer"
    dst = dir.resolve() / "data-analysis"
    copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")
