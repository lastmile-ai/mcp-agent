"""
System/config check for mcp-agent.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcp_agent.config import Settings


app = typer.Typer(help="Check and diagnose mcp-agent configuration")
console = Console()


def _find_files() -> dict[str, Optional[Path]]:
    return {
        "config": Settings.find_config(),
        "secrets": Settings.find_secrets(),
    }


def _get_system_info() -> dict:
    return {
        "platform": platform.platform(),
        "python": sys.version.split(" ")[0],
        "python_path": sys.executable,
    }


def _config_summary(config_path: Optional[Path]) -> dict:
    result = {"status": "not_found", "error": None, "mcp_servers": []}
    if not config_path or not config_path.exists():
        return result
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        result["status"] = "parsed"
        mcp = (data or {}).get("mcp", {})
        servers = (mcp or {}).get("servers", {})
        for name, cfg in servers.items():
            info = {
                "name": name,
                "transport": (cfg or {}).get("transport", "stdio").upper(),
                "command": (cfg or {}).get("command", ""),
                "url": (cfg or {}).get("url", ""),
            }
            result["mcp_servers"].append(info)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


@app.callback(invoke_without_command=True)
def check() -> None:
    files = _find_files()
    sysinfo = _get_system_info()
    summary = _config_summary(files["config"])

    system_table = Table(show_header=False, box=None)
    system_table.add_column("Key", style="cyan")
    system_table.add_column("Value")
    system_table.add_row("Platform", sysinfo["platform"])
    system_table.add_row("Python", sysinfo["python"])
    system_table.add_row("Python Path", sysinfo["python_path"])
    console.print(Panel(system_table, title="System"))

    files_table = Table(show_header=False, box=None)
    files_table.add_column("Setting", style="cyan")
    files_table.add_column("Value")
    cfg = files["config"]
    sec = files["secrets"]
    files_table.add_row("Config", str(cfg) if cfg else "[yellow]Not found[/yellow]")
    files_table.add_row("Secrets", str(sec) if sec else "[yellow]Not found[/yellow]")
    console.print(Panel(files_table, title="Files"))

    servers = summary.get("mcp_servers", [])
    if servers:
        srv_table = Table(show_header=True, header_style="bold")
        srv_table.add_column("Name")
        srv_table.add_column("Transport")
        srv_table.add_column("Command/URL")
        for s in servers:
            target = s["url"] or s["command"]
            srv_table.add_row(s["name"], s["transport"], target)
        console.print(Panel(srv_table, title="MCP Servers"))
