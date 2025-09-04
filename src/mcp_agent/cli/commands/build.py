"""
Build preflight: checks keys, servers, commands; writes manifest.
"""

from __future__ import annotations

import typer
from rich.console import Console
from mcp_agent.config import get_settings
import json
import shutil
from pathlib import Path
import socket


app = typer.Typer(help="Preflight and bundle prep for deployment")
console = Console()


def _check_command(cmd: str) -> bool:
    # Support npx/uvx wrappers always true if present
    parts = cmd.split()
    exe = parts[0]
    return shutil.which(exe) is not None


def _check_url(url: str, timeout: float = 2.0) -> bool:
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
def build(check_only: bool = typer.Option(False, "--check-only")) -> None:
    settings = get_settings()
    ok = True
    report = {
        "providers": {},
        "servers": {},
    }

    # Provider keys
    provs = [
        ("openai", getattr(settings, "openai", None), "api_key"),
        ("anthropic", getattr(settings, "anthropic", None), "api_key"),
        ("google", getattr(settings, "google", None), "api_key"),
        ("azure", getattr(settings, "azure", None), "api_key"),
        ("bedrock", getattr(settings, "bedrock", None), "aws_access_key_id"),
    ]
    for name, obj, keyfield in provs:
        has = bool(getattr(obj, keyfield, None)) if obj else False
        report["providers"][name] = {"configured": has}

    # Servers preflight
    servers = (settings.mcp.servers if settings.mcp else {}) or {}
    for name, s in servers.items():
        status = {"transport": s.transport}
        if s.transport == "stdio":
            status["command"] = s.command
            status["command_found"] = bool(s.command and _check_command(s.command))
            ok = ok and status["command_found"]
        else:
            status["url"] = s.url
            status["reachable"] = bool(s.url and _check_url(s.url))
            # Do not fail build if remote URL is not reachable from local dev
        report["servers"][name] = status

    # Emit manifest
    out_dir = Path(".mcp-agent")
    out_dir.mkdir(exist_ok=True)
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(report, indent=2))
    console.print(f"Wrote manifest: {manifest}")

    if not check_only and not ok:
        typer.secho(
            "Preflight checks failed (missing commands)", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(3)
    if ok:
        console.print("Preflight OK")
