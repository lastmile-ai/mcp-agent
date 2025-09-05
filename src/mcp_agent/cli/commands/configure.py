"""
Client integration helpers: generate client config snippets and optionally write them.

Supported clients:
 - cursor: writes ~/.cursor/mcp.json
 - claude: writes ~/.claude/mcp.json
 - vscode: writes .vscode/mcp.json in project

Behavior:
 - Prints a JSON snippet for the provided server_url.
 - If --write is specified, merges into the appropriate config file.
 - --open prints the target file path (portable alternative to opening file manager).
"""

from __future__ import annotations

import typer
from rich.console import Console
from pathlib import Path
import json

from mcp_agent.cli.utils.url_parser import generate_server_name, parse_server_url


app = typer.Typer(help="Client integration helpers")
console = Console()


def _build_server_entry(url: str, name: str | None = None) -> dict:
    # Distinguish http vs sse based on path suffix
    try:
        _name, transport, fixed_url = parse_server_url(url)
        server_name = name or _name
    except Exception:
        server_name = name or generate_server_name(url)
        fixed_url = url
        transport = "sse" if url.rstrip("/").endswith("/sse") else "http"
    entry = {
        server_name: {
            "url": fixed_url,
            "transport": transport,
        }
    }
    return entry


def _merge_mcp_json(existing: dict, addition: dict) -> dict:
    # Accept a few common shapes and always emit {"mcp":{"servers":{...}}}
    servers: dict = {}
    if isinstance(existing, dict):
        if "mcp" in existing and isinstance(existing.get("mcp"), dict):
            servers = dict(existing["mcp"].get("servers") or {})
        elif "servers" in existing and isinstance(existing.get("servers"), dict):
            servers = dict(existing.get("servers") or {})
        else:
            # Or treat top-level mapping as servers if it looks like name->obj
            for k, v in existing.items():
                if isinstance(v, dict) and ("url" in v or "transport" in v):
                    servers[k] = v
    # Merge
    servers.update(addition)
    return {"mcp": {"servers": servers}}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _print_output(data: dict, fmt: str) -> None:
    if fmt.lower() == "json":
        console.print_json(data=data)
    else:
        # Text summary
        try:
            name = next(iter(data["mcp"]["servers"].keys()))
        except Exception:
            name = "server"
        console.print(f"Add this to your client's mcp.json under servers: '{name}'")
        console.print_json(data=data)


@app.callback(invoke_without_command=True)
def configure(
    server_url: str = typer.Argument(...),
    client: str = typer.Option(
        ..., "--client", help="cursor|claude|vscode|smithery|mcp.run"
    ),
    write: bool = typer.Option(False, "--write"),
    open: bool = typer.Option(False, "--open"),
    format: str = typer.Option("text", "--format", help="text|json"),
    name: str | None = typer.Option(
        None, "--name", help="Optional server name override"
    ),
) -> None:
    client_lc = client.lower()
    entry = _build_server_entry(server_url, name=name)
    snippet = {"mcp": {"servers": entry}}

    target: Path | None = None
    if client_lc == "cursor":
        target = Path.home() / ".cursor" / "mcp.json"
    elif client_lc == "claude":
        target = Path.home() / ".claude" / "mcp.json"
    elif client_lc == "vscode":
        target = Path.cwd() / ".vscode" / "mcp.json"
    elif client_lc == "smithery":
        # Smithery uses a project-local config
        target = Path.cwd() / ".smithery" / "mcp.json"
    elif client_lc == "mcp.run":
        # mcp.run typically uses a web interface, just print config
        console.print("[yellow]mcp.run uses web interface for configuration.[/yellow]")
        console.print("Copy this configuration to your mcp.run dashboard:")
        _print_output(snippet, format)
        return
    else:
        # Unknown/unsupported: print snippet only
        console.print(f"[yellow]Client '{client}' not directly supported.[/yellow]")
        console.print("Use this configuration snippet in your client:")
        _print_output(snippet, format)
        return

    if write:
        try:
            if target.exists():
                existing = json.loads(target.read_text(encoding="utf-8"))
            else:
                existing = {}
        except Exception:
            existing = {}
        merged = _merge_mcp_json(existing, entry)
        try:
            _write_json(target, merged)
            console.print(f"Wrote config to {target}")
        except Exception as e:
            typer.secho(f"Failed to write: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(5)
        if open:
            console.print(str(target))
        else:
            # Also print snippet for visibility
            _print_output(merged, format)
    else:
        _print_output(snippet, format)
