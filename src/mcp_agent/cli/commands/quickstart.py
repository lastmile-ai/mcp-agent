"""
Quickstart examples: scaffolded adapters over repository examples.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from importlib.resources import files as _pkg_files

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
    try:
        if dst.exists():
            if force:
                shutil.rmtree(dst)
            else:
                return 0
        shutil.copytree(src, dst)
        return 1
    except Exception:
        return 0


def _copy_pkg_tree(pkg_rel: str, dst: Path, force: bool) -> int:
    """Copy packaged examples from mcp_agent.data/examples/<pkg_rel> into dst.

    Uses importlib.resources to locate files installed with the package.
    """
    try:
        root = (
            _pkg_files("mcp_agent")
            .joinpath("data")
            .joinpath("examples")
            .joinpath(pkg_rel)
        )
    except Exception:
        return 0
    if not root.exists():
        return 0

    # Mirror directory tree
    def _copy_any(node, target: Path):
        if node.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in node.iterdir():
                _copy_any(child, target / child.name)
        else:
            if target.exists() and not force:
                return
            with node.open("rb") as rf:
                data = rf.read()
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as wf:
                wf.write(data)

    _copy_any(root, dst)
    return 1


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
        ("mcp-basic-agent", "data/examples/basic/mcp_basic_agent"),
        ("token-counter", "data/examples/basic/token_counter"),
        ("agent-factory", "data/examples/basic/agent_factory"),
        ("basic-agent-server", "data/examples/mcp_agent_server/asyncio"),
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


@app.command("mcp-basic-agent")
def mcp_basic_agent(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    dst = dir.resolve() / "mcp_basic_agent"
    copied = _copy_pkg_tree("basic/mcp_basic_agent", dst, force)
    if not copied:
        # fallback to repo examples
        src = EXAMPLE_ROOT / "basic" / "mcp_basic_agent"
        copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("token-counter")
def token_counter(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    dst = dir.resolve() / "token_counter"
    copied = _copy_pkg_tree("basic/token_counter", dst, force)
    if not copied:
        src = EXAMPLE_ROOT / "basic" / "token_counter"
        copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("agent-factory")
def agent_factory(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    dst = dir.resolve() / "agent_factory"
    copied = _copy_pkg_tree("basic/agent_factory", dst, force)
    if not copied:
        src = EXAMPLE_ROOT / "basic" / "agent_factory"
        copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")


@app.command("basic-agent-server")
def basic_agent_server(
    dir: Path = typer.Argument(Path(".")),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    dst = dir.resolve() / "basic_agent_server"
    copied = _copy_pkg_tree("mcp_agent_server/asyncio", dst, force)
    if not copied:
        src = EXAMPLE_ROOT / "mcp_agent_server" / "asyncio"
        copied = _copy_tree(src, dst, force)
    console.print(f"Copied {copied} set(s) to {dst}")
