"""
Config command group: show, check, edit (scaffold).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcp_agent.config import Settings


app = typer.Typer(help="Configuration utilities")
console = Console()


def _find_config_file() -> Optional[Path]:
    return Settings.find_config()


def _find_secrets_file() -> Optional[Path]:
    return Settings.find_secrets()


@app.command("show")
def show(
    secrets: bool = typer.Option(False, "--secrets", "-s", help="Show secrets file"),
    path: Optional[Path] = typer.Argument(None, help="Optional explicit path"),
) -> None:
    """Print the current config or secrets file with YAML validation."""
    file_path = path
    if file_path is None:
        file_path = _find_secrets_file() if secrets else _find_config_file()
    if not file_path or not file_path.exists():
        typer.secho("Config file not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    console.print(f"\n[bold]{'secrets' if secrets else 'config'}:[/bold] {file_path}\n")
    try:
        text = file_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text)
        console.print("[green]YAML syntax is valid[/green]")
        if parsed is None:
            console.print("[yellow]Warning: file empty[/yellow]")
        console.print(text)
    except Exception as e:
        typer.secho(f"Error parsing YAML: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(5)


@app.command("check")
def check() -> None:
    """Summarize system+config+keys quickly."""
    cfg = _find_config_file()
    sec = _find_secrets_file()

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Config", str(cfg) if cfg else "[red]not found[/red]")
    table.add_row("Secrets", str(sec) if sec else "[yellow]not found[/yellow]")

    # Basic settings load (merges secrets if next to config via Settings.get)
    try:
        settings = Settings() if cfg is None else Settings(**yaml.safe_load(cfg.read_text()))
        # Show a small summary
        table.add_row("Execution Engine", settings.execution_engine)
        if settings.logger:
            table.add_row("Logger.level", settings.logger.level)
            table.add_row("Logger.type", settings.logger.type)
        mcp_servers = list((settings.mcp.servers or {}).keys()) if settings.mcp else []
        table.add_row("MCP servers", ", ".join(mcp_servers) or "(none)")
    except Exception as e:
        table.add_row("Load error", f"[red]{e}[/red]")

    console.print(Panel(table, title="mcp-agent config"))


@app.command("edit")
def edit(secrets: bool = typer.Option(False, "--secrets", "-s")) -> None:
    """Open config or secrets in $EDITOR (scaffold)."""
    # Minimal scaffold: print path and exit; full EDITOR support can be added later
    target = _find_secrets_file() if secrets else _find_config_file()
    if not target:
        typer.secho("No file found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    console.print(str(target))


