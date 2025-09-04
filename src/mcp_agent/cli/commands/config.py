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
        settings = (
            Settings() if cfg is None else Settings(**yaml.safe_load(cfg.read_text()))
        )
        # Show a small summary
        table.add_row("Execution Engine", settings.execution_engine)
        if settings.logger:
            table.add_row("Logger.level", settings.logger.level)
            table.add_row("Logger.type", settings.logger.type)
        if settings.otel and settings.otel.enabled:
            # Summarize OTEL exporters
            try:
                exporters = settings.otel.exporters or []

                def _fmt(e):
                    if isinstance(e, str):
                        return e
                    t = getattr(e, "type", None)
                    if t == "otlp":
                        endpoint = getattr(e, "endpoint", None) or (
                            settings.otel.otlp_settings.endpoint
                            if settings.otel.otlp_settings
                            else None
                        )
                        return f"otlp({endpoint or 'no-endpoint'})"
                    if t == "file":
                        path = getattr(e, "path", None) or settings.otel.path
                        return f"file({path or 'auto'})"
                    return t or str(e)

                table.add_row("OTEL.enabled", "true")
                table.add_row(
                    "OTEL.exporters", ", ".join(_fmt(e) for e in exporters) or "(none)"
                )
                table.add_row("OTEL.sample_rate", str(settings.otel.sample_rate))
            except Exception as _:
                table.add_row("OTEL", "[red]error summarizing exporters[/red]")
        mcp_servers = list((settings.mcp.servers or {}).keys()) if settings.mcp else []
        table.add_row("MCP servers", ", ".join(mcp_servers) or "(none)")
    except Exception as e:
        table.add_row("Load error", f"[red]{e}[/red]")

    console.print(Panel(table, title="mcp-agent config"))


@app.command("edit")
def edit(secrets: bool = typer.Option(False, "--secrets", "-s")) -> None:
    """Open config or secrets in $EDITOR, falling back to common editors."""
    target = _find_secrets_file() if secrets else _find_config_file()
    if not target:
        typer.secho("No file found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    import os
    import subprocess

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    candidates = [editor] if editor else []
    candidates += ["code --wait", "nano", "vi"]

    for cmd in candidates:
        if not cmd:
            continue
        try:
            subprocess.run(f"{cmd} {str(target)}", shell=True, check=True)
            return
        except Exception:
            continue
    # If all fail, just print the path
    console.print(str(target))


@app.command("init")
def init_builder() -> None:
    """Interactive builder for config and secrets files."""
    import yaml
    from mcp_agent.config import Settings as _Settings

    console.print("\n[bold]mcp-agent config init[/bold]\n")

    # Prompts
    use_filesystem = typer.confirm("Add filesystem server recipe?", default=False)
    use_fetch = typer.confirm("Add fetch server recipe?", default=False)
    logger_type = typer.prompt(
        "Logger type (none|console|file|http)", default="console"
    )
    logger_level = typer.prompt(
        "Logger level (debug|info|warning|error)", default="info"
    )
    log_path = None
    if logger_type == "file":
        log_path = typer.prompt("Log file path", default="mcp-agent.jsonl")
    otel_enabled = typer.confirm("Enable OpenTelemetry?", default=False)
    default_openai = typer.prompt("Default OpenAI model (optional)", default="")
    default_anthropic = typer.prompt("Default Anthropic model (optional)", default="")

    # Start from packaged template
    try:
        tmpl_cfg = (
            Path(__file__).parents[3] / "data" / "templates" / "config_basic.yaml"
        ).read_text(encoding="utf-8")
        cfg: dict = yaml.safe_load(tmpl_cfg) or {}
    except Exception:
        cfg = {
            "mcp": {"servers": {}},
            "logger": {"type": logger_type, "level": logger_level},
            "otel": {"enabled": bool(otel_enabled)},
        }
    # Apply choices
    cfg.setdefault("logger", {})
    cfg["logger"]["type"] = logger_type
    cfg["logger"]["level"] = logger_level
    cfg.setdefault("otel", {})
    cfg["otel"]["enabled"] = bool(otel_enabled)
    if logger_type == "file" and log_path:
        cfg["logger"]["path"] = log_path

    if use_filesystem:
        cfg["mcp"]["servers"]["filesystem"] = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        }
    if use_fetch:
        cfg["mcp"]["servers"]["fetch"] = {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-fetch"],
        }

    if default_openai:
        cfg["openai"] = {"default_model": default_openai}
    if default_anthropic:
        cfg["anthropic"] = {"default_model": default_anthropic}

    # Secrets prompts
    write_secrets = typer.confirm("Write secrets file now?", default=True)
    secrets: dict = {}
    if write_secrets:
        if typer.confirm("Set OpenAI API key?", default=False):
            secrets.setdefault("openai", {})["api_key"] = typer.prompt("OPENAI_API_KEY")
        if typer.confirm("Set Anthropic API key?", default=False):
            secrets.setdefault("anthropic", {})["api_key"] = typer.prompt(
                "ANTHROPIC_API_KEY"
            )

    # Write files
    cfg_path = _find_config_file() or (Path.cwd() / "mcp_agent.config.yaml")
    try:
        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        console.print(f"[green]Wrote[/green] {cfg_path}")
    except Exception as e:
        typer.secho(f"Failed to write config: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)

    if secrets is not None:
        try:
            tmpl_sec = (
                Path(__file__).parents[3] / "data" / "templates" / "secrets_basic.yaml"
            ).read_text(encoding="utf-8")
        except Exception:
            tmpl_sec = ""
        merged = {}
        if tmpl_sec:
            try:
                merged = yaml.safe_load(tmpl_sec) or {}
            except Exception:
                merged = {}
        if isinstance(secrets, dict):
            # Overlay user-provided keys
            for k, v in secrets.items():
                merged.setdefault(k, {}).update(v if isinstance(v, dict) else {})
        sec_path = _find_secrets_file() or (Path.cwd() / "mcp_agent.secrets.yaml")
        try:
            sec_path.write_text(
                yaml.safe_dump(merged, sort_keys=False), encoding="utf-8"
            )
            console.print(f"[green]Wrote[/green] {sec_path}")
        except Exception as e:
            typer.secho(f"Failed to write secrets: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(5)
