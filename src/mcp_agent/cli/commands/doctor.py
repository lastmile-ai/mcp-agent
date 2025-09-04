"""
Doctor: comprehensive diagnostics for config/secrets/keys/servers/network.
"""

from __future__ import annotations

import platform
import sys
import shutil
import socket

import typer
from rich.console import Console
from rich.table import Table
from mcp_agent.config import get_settings


app = typer.Typer(help="Comprehensive diagnostics")
console = Console()


def _check_host(url: str, timeout: float = 1.5) -> bool:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


@app.callback(invoke_without_command=True)
def doctor() -> None:
    sys_table = Table(show_header=False, box=None)
    sys_table.add_column("Key", style="cyan")
    sys_table.add_column("Value")
    sys_table.add_row("OS", platform.platform())
    sys_table.add_row("Python", sys.version.split(" ")[0])
    sys_table.add_row("Typer", "present")
    console.print(sys_table)

    settings = get_settings()

    # Providers
    prov_table = Table(show_header=True)
    prov_table.add_column("Provider")
    prov_table.add_column("Configured")
    for name in ["openai", "anthropic", "google", "azure", "bedrock"]:
        obj = getattr(settings, name, None)
        key = getattr(obj, "api_key", None) if obj else None
        prov_table.add_row(name, "yes" if key else "no")
    console.print(prov_table)

    # Servers
    srv_table = Table(show_header=True)
    srv_table.add_column("Name")
    srv_table.add_column("Transport")
    srv_table.add_column("Target")
    srv_table.add_column("OK")
    servers = (settings.mcp.servers if settings.mcp else {}) or {}
    for name, s in servers.items():
        ok = True
        tgt = s.url or s.command or ""
        if s.transport == "stdio":
            ok = bool(s.command and shutil.which(s.command))
        else:
            ok = bool(s.url and _check_host(s.url))
        srv_table.add_row(name, s.transport, tgt, "yes" if ok else "no")
    console.print(srv_table)

    # Logger/OTEL summary
    misc_table = Table(show_header=False, box=None)
    misc_table.add_column("Setting", style="cyan")
    misc_table.add_column("Value")
    if settings.logger:
        misc_table.add_row("Logger.level", settings.logger.level)
        misc_table.add_row("Logger.type", settings.logger.type)
        misc_table.add_row("Logger.path", getattr(settings.logger, "path", ""))
    if settings.otel and settings.otel.enabled:
        exporters = settings.otel.exporters or []
        types = []
        for e in exporters:
            t = getattr(e, "type", None) or str(e)
            types.append(t)
        misc_table.add_row("OTEL.enabled", "true")
        misc_table.add_row("OTEL.exporters", ", ".join(types))
    console.print(misc_table)
