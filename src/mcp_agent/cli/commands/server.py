"""
Local server helpers: add/import/list/test (initial scaffolding for add/list/test).
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mcp_agent.config import Settings, MCPServerSettings, MCPSettings
from mcp_agent.cli.utils.importers import import_servers_from_mcp_json


app = typer.Typer(help="Local server helpers")
console = Console()


def _load_config_yaml(path: Settings | None = None):
    import yaml

    cfg_path = Settings.find_config()
    data = {}
    if cfg_path and cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text()) or {}
        except Exception:
            data = {}
    return cfg_path, data


def _persist_server_entry(name: str, settings: MCPServerSettings) -> None:
    import yaml

    cfg_path, data = _load_config_yaml()
    # Ensure structure
    if "mcp" not in data:
        data["mcp"] = {}
    if "servers" not in data["mcp"] or data["mcp"]["servers"] is None:
        data["mcp"]["servers"] = {}
    # Build plain dict from settings
    entry = {
        "transport": settings.transport,
    }
    if settings.transport == "stdio":
        if settings.command:
            entry["command"] = settings.command
        if settings.args:
            entry["args"] = settings.args
        if settings.env:
            entry["env"] = settings.env
    else:
        if settings.url:
            entry["url"] = settings.url
        if settings.headers:
            entry["headers"] = settings.headers

    data["mcp"]["servers"][name] = entry

    # Decide path to write
    if not cfg_path:
        cfg_path = Settings.find_config() or Settings.find_config()  # try discovery
        if not cfg_path:
            cfg_path = Settings.find_config()
    # If discovery failed, write to default file in CWD
    if not cfg_path:
        cfg_path = Settings.find_config() or None
    # Fallback path in CWD
    from pathlib import Path as _Path

    if not cfg_path:
        cfg_path = _Path("mcp_agent.config.yaml")

    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
    console.print(f"Wrote server '{name}' to {cfg_path}")


@app.command("list")
def list_servers() -> None:
    settings = Settings()
    servers = (settings.mcp.servers if settings.mcp else {}) or {}
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Transport")
    table.add_column("URL/Command")
    for name, s in servers.items():
        target = s.url or s.command or ""
        table.add_row(name, s.transport, target)
    console.print(table)


@app.command("add")
def add(
    kind: str = typer.Argument(..., help="http|sse|stdio|npx|uvx|dxt|recipe"),
    value: str = typer.Argument(..., help="url or quoted command or recipe name"),
    name: Optional[str] = typer.Option(None, "--name"),
    auth: Optional[str] = typer.Option(None, "--auth"),
    write: bool = typer.Option(
        True, "--write/--no-write", help="Persist to config file"
    ),
) -> None:
    settings = Settings()
    if settings.mcp is None:
        settings.mcp = MCPSettings()
    servers = settings.mcp.servers
    entry = MCPServerSettings()
    if kind == "dxt":
        # Treat value as path to .dxt (zip) or manifest directory
        try:
            import zipfile
            from pathlib import Path as _Path
            import json

            p = _Path(value).expanduser().resolve()
            extract_dir = _Path(".mcp-agent") / "extensions"
            extract_dir.mkdir(parents=True, exist_ok=True)
            target_dir = None
            if p.suffix.lower() == ".dxt" and p.is_file():
                with zipfile.ZipFile(p, "r") as zf:
                    base = p.stem
                    target_dir = extract_dir / base
                    if target_dir.exists():
                        # Overwrite
                        import shutil

                        shutil.rmtree(target_dir)
                    zf.extractall(target_dir)
            elif p.is_dir():
                target_dir = p
            else:
                raise ValueError("DXT path must be a .dxt file or a directory")

            manifest = None
            for cand in [target_dir / "manifest.json", target_dir / "package.json"]:
                if cand.exists():
                    manifest = json.loads(cand.read_text())
                    break
            if not manifest:
                raise ValueError("manifest.json not found in DXT package")

            server_name = name or manifest.get("name") or target_dir.name
            # Try common fields
            stdio = manifest.get("stdio") or {}
            cmd = stdio.get("command") or manifest.get("command")
            args = stdio.get("args") or manifest.get("args") or []
            env = stdio.get("env") or manifest.get("env") or {}
            if not cmd:
                raise ValueError("DXT manifest missing stdio command")
            entry.transport = "stdio"
            entry.command = cmd
            entry.args = args
            entry.env = env
            servers[server_name] = entry
            if write:
                _persist_server_entry(server_name, entry)
            console.print(f"Added DXT server '{server_name}' => {cmd} {args}")
            return
        except Exception as e:
            typer.secho(f"Failed to add dxt server: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(5)
    elif kind == "recipe":
        recipes = {
            "filesystem": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            },
            "fetch": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
            },
            # Add a safe 'roots' recipe using server-filesystem with roots mapping
            # Users can later edit config to customize
            "roots": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            },
        }
        rec = recipes.get(value)
        if not rec:
            typer.secho("Unknown recipe", err=True, fg=typer.colors.RED)
            raise typer.Exit(6)
        entry.transport = rec["transport"]
        entry.command = rec.get("command")
        entry.args = rec.get("args") or []
        srv_name = name or value
        servers[srv_name] = entry
        if write:
            _persist_server_entry(srv_name, entry)
        console.print(f"Added recipe server '{srv_name}'")
        return
    elif kind in ("http", "sse"):
        entry.transport = kind
        entry.url = value
        if auth:
            entry.headers = {"Authorization": f"Bearer {auth}"}
    else:
        entry.transport = "stdio"
        # naive split; robust parsing can be added later
        parts = value.split()
        entry.command = parts[0]
        entry.args = parts[1:]
    srv_name = name or (value.split("/")[-1] if kind in ("http", "sse") else parts[0])
    servers[srv_name] = entry
    if write:
        _persist_server_entry(srv_name, entry)
    console.print(f"Added server '{srv_name}' (not yet persisted)")


@app.command("test")
def test(name: str, timeout: float = typer.Option(10.0, "--timeout")) -> None:
    """Initialize app context, connect to server, and print capabilities/tools."""
    import asyncio
    from mcp_agent.app import MCPApp
    from mcp_agent.agents.agent import Agent

    async def _probe():
        app_obj = MCPApp(name="server-test")
        async with app_obj.run():
            agent = Agent(name="probe", server_names=[name], context=app_obj.context)
            async with agent:
                caps = await agent.get_capabilities(server_name=name)
                console.print("Capabilities:")
                console.print(caps)
                tools = await agent.list_tools(server_name=name)
                console.print("Tools:")
                for t in tools.tools:
                    console.print(f"- {t.name}")
                resources = await agent.list_resources(server_name=name)
                console.print("Resources:")
                for r in resources.resources:
                    console.print(f"- {r.uri}")

    try:
        asyncio.run(_probe())
    except Exception as e:
        typer.secho(f"Server test failed: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)


# Import subcommands
import_app = typer.Typer(help="Import server configs from common sources")


@import_app.command("dxt")
def import_dxt(path: str, name: Optional[str] = typer.Option(None, "--name")) -> None:
    """Import a Desktop Extension (.dxt or manifest dir) and persist server entry."""
    add(kind="dxt", value=path, name=name, write=True)


@import_app.command("mcp-json")
def import_mcp_json(path: str) -> None:
    """Import servers from a cursor/vscode style mcp.json and persist entries."""
    from pathlib import Path as _Path

    p = _Path(path).expanduser().resolve()
    if not p.exists():
        typer.secho("mcp.json not found", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    try:
        imported = import_servers_from_mcp_json(p)
        if not imported:
            console.print("No servers found in mcp.json")
            return
        for name, cfg in imported.items():
            _persist_server_entry(name, cfg)
        console.print(f"Imported {len(imported)} servers from {p}")
    except Exception as e:
        typer.secho(f"Import failed: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)


app.add_typer(import_app, name="import")


# Convenience imports for common client configs
@import_app.command("cursor")
def import_cursor() -> None:
    """Import servers from common Cursor locations (mcp.json)."""
    from pathlib import Path as _Path

    candidates = [
        _Path(".cursor/mcp.json").resolve(),
        _Path.home() / ".cursor/mcp.json",
    ]
    imported_any = False
    for p in candidates:
        if p.exists():
            try:
                imported = import_servers_from_mcp_json(p)
                for name, cfg in imported.items():
                    _persist_server_entry(name, cfg)
                    imported_any = True
            except Exception:
                continue
    if imported_any:
        console.print("Imported servers from Cursor mcp.json")
    else:
        console.print("No Cursor mcp.json found")


@import_app.command("vscode")
def import_vscode() -> None:
    """Import servers from common VSCode locations (mcp.json)."""
    from pathlib import Path as _Path

    candidates = [
        _Path(".vscode/mcp.json").resolve(),
        _Path.cwd() / "mcp.json",
    ]
    imported_any = False
    for p in candidates:
        if p.exists():
            try:
                imported = import_servers_from_mcp_json(p)
                for name, cfg in imported.items():
                    _persist_server_entry(name, cfg)
                    imported_any = True
            except Exception:
                continue
    if imported_any:
        console.print("Imported servers from VSCode mcp.json")
    else:
        console.print("No VSCode mcp.json found")


@import_app.command("claude")
def import_claude() -> None:
    """Import servers from common Claude Code locations (mcp.json)."""
    from pathlib import Path as _Path

    candidates = [
        _Path(".claude/mcp.json").resolve(),
        _Path.home() / ".claude/mcp.json",
    ]
    imported_any = False
    for p in candidates:
        if p.exists():
            try:
                imported = import_servers_from_mcp_json(p)
                for name, cfg in imported.items():
                    _persist_server_entry(name, cfg)
                    imported_any = True
            except Exception:
                continue
    if imported_any:
        console.print("Imported servers from Claude mcp.json")
    else:
        console.print("No Claude mcp.json found")
