"""
Models command group: list and set-default (scaffold).
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from mcp_agent.workflows.llm.llm_selector import load_default_models


app = typer.Typer(help="List and manage models")
console = Console()


@app.command("list")
def list_models(
    format: str = typer.Option("text", "--format"),
    min_context: int = typer.Option(
        None, "--min-context", help="Minimum context window size"
    ),
    tool_use: bool = typer.Option(
        None, "--tool-use", help="Filter by tool calling capability"
    ),
    provider: str = typer.Option(
        None, "--provider", help="Filter by provider name (case-insensitive)"
    ),
) -> None:
    """List known model catalog (from embedded benchmarks)."""
    models = load_default_models()

    if min_context is not None:
        models = [
            m for m in models if m.context_window and m.context_window >= min_context
        ]
    if tool_use is not None:
        models = [m for m in models if m.tool_calling == tool_use]
    if provider is not None:
        models = [m for m in models if provider.lower() in m.provider.lower()]

    # Sort models alphabetically by provider, then by model name
    models = sorted(models, key=lambda m: (m.provider, m.name))
    if format.lower() == "json":
        data = [m.model_dump() for m in models]
        console.print_json(json.dumps(data))
        return
    if format.lower() == "yaml":
        try:
            import yaml  # type: ignore

            console.print(
                yaml.safe_dump([m.model_dump() for m in models], sort_keys=False)
            )
            return
        except Exception:
            pass

    table = Table(show_header=True, header_style="bold", title="Models")
    table.add_column("Provider")
    table.add_column("Name")
    table.add_column("Context")
    table.add_column("Tool use")
    for m in models:
        table.add_row(
            m.provider,
            m.name,
            str(m.context_window or ""),
            "✔" if m.tool_calling else "",
        )
    console.print(table)


@app.command("set-default")
def set_default(
    name: str = typer.Argument(..., help="Provider-qualified name"),
) -> None:
    """Set provider default model in config, writing to discovered file."""
    import yaml
    from mcp_agent.config import Settings

    cfg_path = Settings.find_config()
    if not cfg_path or not cfg_path.exists():
        typer.secho("Config file not found", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)

    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
        # name may be provider.model or provider:model
        prov = None
        model_name = name
        if ":" in name:
            prov, model_name = name.split(":", 1)
        elif "." in name:
            parts = name.split(".", 1)
            prov, model_name = parts[0], parts[1]
        prov = (prov or "openai").lower()

        # Ensure provider section exists, set default_model
        if prov not in data:
            data[prov] = {}
        data[prov]["default_model"] = model_name

        cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
        console.print(f"Updated {cfg_path} -> {prov}.default_model = {model_name}")
    except Exception as e:
        typer.secho(f"Failed to update config: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)
