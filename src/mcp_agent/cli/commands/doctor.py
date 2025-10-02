"""
Doctor: comprehensive diagnostics for config/secrets/keys/servers/network.
"""

from __future__ import annotations

import os
import platform
import sys
import shutil
import socket
from pathlib import Path
from typing import List, Optional, Tuple

import typer
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from mcp_agent.config import get_settings, Settings


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


def _check_config_file(path: Optional[Path]) -> Tuple[str, Optional[str]]:
    """Check config file status: not_found, error, or valid."""
    if not path:
        return "not_found", None
    if not path.exists():
        return "not_found", None
    try:
        with open(path, "r") as f:
            yaml.safe_load(f)
        return "valid", None
    except Exception as e:
        return "error", str(e)


def _check_secrets_file(path: Optional[Path]) -> Tuple[str, Optional[str], dict]:
    """Check secrets file status and extract keys info."""
    secrets = {}
    if not path:
        return "not_found", None, secrets
    if not path.exists():
        return "not_found", None, secrets
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return "valid", None, data
    except Exception as e:
        return "error", str(e), secrets


def _check_provider_keys(settings: Settings, secrets: dict) -> dict:
    """Check availability of provider API keys."""
    providers = {
        "openai": {"env": "OPENAI_API_KEY", "configured": False, "source": None},
        "anthropic": {"env": "ANTHROPIC_API_KEY", "configured": False, "source": None},
        "google": {"env": "GOOGLE_API_KEY", "configured": False, "source": None},
        "azure": {"env": "AZURE_API_KEY", "configured": False, "source": None},
        "bedrock": {"env": "AWS_ACCESS_KEY_ID", "configured": False, "source": None},
    }

    for name, info in providers.items():
        # Check environment variable
        if os.getenv(info["env"]):
            info["configured"] = True
            info["source"] = "env"
            continue

        # Check settings object
        provider_obj = getattr(settings, name, None)
        if provider_obj and getattr(provider_obj, "api_key", None):
            info["configured"] = True
            info["source"] = "config"
            continue

        # Check secrets dict
        if name in secrets and secrets[name].get("api_key"):
            info["configured"] = True
            info["source"] = "secrets"

    return providers


def _check_command_availability() -> dict:
    """Check if common commands are available."""
    commands = {
        "npx": shutil.which("npx") is not None,
        "uvx": shutil.which("uvx") is not None,
        "uv": shutil.which("uv") is not None,
        "python": shutil.which("python") is not None,
        "python3": shutil.which("python3") is not None,
        "git": shutil.which("git") is not None,
        "docker": shutil.which("docker") is not None,
    }
    return commands


def _generate_suggestions(
    config_status: str,
    secrets_status: str,
    providers: dict,
    servers: dict,
    commands: dict,
    settings: Settings,
) -> List[str]:
    """Generate actionable suggestions based on diagnostics."""
    suggestions = []

    # Config/secrets suggestions
    if config_status == "not_found":
        suggestions.append(
            "[yellow]No config file found.[/yellow] Run [cyan]mcp-agent init[/cyan] to create one."
        )
    elif config_status == "error":
        suggestions.append(
            "[red]Config file has syntax errors.[/red] Run [cyan]mcp-agent config edit[/cyan] to fix."
        )

    if secrets_status == "not_found":
        suggestions.append(
            "[yellow]No secrets file found.[/yellow] Run [cyan]mcp-agent keys set <provider> <key>[/cyan] or create mcp_agent.secrets.yaml"
        )
    elif secrets_status == "error":
        suggestions.append(
            "[red]Secrets file has syntax errors.[/red] Check YAML syntax in mcp_agent.secrets.yaml"
        )

    # Provider key suggestions
    no_keys = [p for p, info in providers.items() if not info["configured"]]
    if no_keys:
        suggestions.append(
            f"[yellow]Missing API keys for: {', '.join(no_keys)}[/yellow]\n"
            f"  Set with: [cyan]mcp-agent keys set <provider> <key>[/cyan]\n"
            f"  Or export: {', '.join([providers[p]['env'] for p in no_keys])}"
        )

    # Command availability
    if not commands["npx"] and any(
        s.command == "npx"
        for s in (servers.values() if isinstance(servers, dict) else servers)
    ):
        suggestions.append(
            "[yellow]npx not found but required by servers.[/yellow] Install Node.js from https://nodejs.org"
        )

    if not commands["uvx"] and not commands["uv"]:
        suggestions.append(
            "[dim]Consider installing uv for Python package management: https://github.com/astral-sh/uv[/dim]"
        )

    # Logger suggestions
    if (
        settings.logger
        and settings.logger.type == "file"
        and not getattr(settings.logger, "path", None)
    ):
        suggestions.append(
            "[yellow]Logger type 'file' requires 'path' setting.[/yellow] Add logger.path to config."
        )

    # OTEL suggestions
    if settings.otel and settings.otel.enabled:
        try:
            for e in settings.otel.exporters or []:
                if getattr(e, "type", None) == "otlp" and not getattr(
                    e, "endpoint", None
                ):
                    suggestions.append(
                        "[yellow]OTLP exporter enabled without endpoint.[/yellow] Add endpoint to otel.exporters config."
                    )
        except Exception:
            pass

    return suggestions


@app.callback(invoke_without_command=True)
def doctor() -> None:
    """Run comprehensive diagnostics and provide actionable suggestions."""

    console.print("\n[bold cyan]MCP-Agent Doctor[/bold cyan] - System Diagnostics\n")

    # System Information
    sys_table = Table(title="System Information", show_header=False, box=None)
    sys_table.add_column("Key", style="cyan")
    sys_table.add_column("Value")
    sys_table.add_row("OS", platform.platform())
    sys_table.add_row("Python", sys.version.split(" ")[0])
    sys_table.add_row("Python Path", sys.executable)

    # Check for mcp-agent installation
    try:
        from importlib.metadata import version

        mcp_version = version("mcp-agent")
    except Exception:
        mcp_version = "development"
    sys_table.add_row("MCP-Agent", mcp_version)

    console.print(Panel(sys_table, border_style="blue"))

    # Load settings and check files
    settings = get_settings()
    config_path = Settings.find_config()
    secrets_path = Settings.find_secrets()

    config_status, config_error = _check_config_file(config_path)
    secrets_status, secrets_error, secrets_data = _check_secrets_file(secrets_path)

    # Configuration Files Status
    files_table = Table(title="Configuration Files", show_header=True)
    files_table.add_column("File", style="cyan")
    files_table.add_column("Status")
    files_table.add_column("Path")

    # Config file status
    config_status_display = {
        "valid": "[green]✓ Valid[/green]",
        "error": "[red]✗ Error[/red]",
        "not_found": "[yellow]⚠ Not Found[/yellow]",
    }[config_status]
    files_table.add_row(
        "Config", config_status_display, str(config_path) if config_path else "-"
    )

    # Secrets file status
    secrets_status_display = {
        "valid": "[green]✓ Valid[/green]",
        "error": "[red]✗ Error[/red]",
        "not_found": "[yellow]⚠ Not Found[/yellow]",
    }[secrets_status]
    files_table.add_row(
        "Secrets", secrets_status_display, str(secrets_path) if secrets_path else "-"
    )

    if config_error:
        files_table.add_row("", f"[red]{config_error}[/red]", "")
    if secrets_error:
        files_table.add_row("", f"[red]{secrets_error}[/red]", "")

    console.print(Panel(files_table, border_style="blue"))

    # Provider Keys Status
    providers = _check_provider_keys(settings, secrets_data)

    prov_table = Table(title="Provider API Keys", show_header=True)
    prov_table.add_column("Provider", style="cyan")
    prov_table.add_column("Status")
    prov_table.add_column("Source")
    prov_table.add_column("Environment Variable")

    for name, info in providers.items():
        status = "[green]✓[/green]" if info["configured"] else "[red]✗[/red]"
        source = info["source"] or "-"
        prov_table.add_row(name.capitalize(), status, source, info["env"])

    console.print(Panel(prov_table, border_style="blue"))

    # Command Availability
    commands = _check_command_availability()

    cmd_table = Table(title="System Commands", show_header=True)
    cmd_table.add_column("Command", style="cyan")
    cmd_table.add_column("Available")
    cmd_table.add_column("Required For")

    cmd_requirements = {
        "npx": "NPM-based MCP servers",
        "uvx": "Python MCP servers (fast)",
        "uv": "Python package management",
        "python": "Python scripts",
        "python3": "Python 3 scripts",
        "git": "Version control",
        "docker": "Containerized servers",
    }

    for cmd, available in commands.items():
        status = "[green]✓[/green]" if available else "[yellow]✗[/yellow]"
        requirement = cmd_requirements.get(cmd, "")
        cmd_table.add_row(cmd, status, requirement)

    console.print(Panel(cmd_table, border_style="blue"))

    # MCP Servers Status
    servers = (settings.mcp.servers if settings.mcp else {}) or {}

    if servers:
        srv_table = Table(title="MCP Servers", show_header=True)
        srv_table.add_column("Name", style="cyan")
        srv_table.add_column("Transport")
        srv_table.add_column("Status")
        srv_table.add_column("Target")

        for name, s in servers.items():
            ok = True
            reason = ""
            tgt = s.url or s.command or ""

            if s.transport == "stdio":
                if s.command:
                    if not shutil.which(s.command):
                        ok = False
                        reason = "command not found"
                else:
                    ok = False
                    reason = "no command"
            else:
                if s.url:
                    if not _check_host(s.url):
                        ok = False
                        reason = "unreachable"
                else:
                    ok = False
                    reason = "no URL"

            status = "[green]✓[/green]" if ok else f"[red]✗ {reason}[/red]"

            # Truncate long targets
            if len(tgt) > 40:
                tgt = tgt[:37] + "..."

            srv_table.add_row(name, s.transport, status, tgt)

        console.print(Panel(srv_table, border_style="blue"))

    # Logger Configuration
    if settings.logger:
        log_table = Table(title="Logger Configuration", show_header=False, box=None)
        log_table.add_column("Setting", style="cyan")
        log_table.add_column("Value")

        log_table.add_row("Level", settings.logger.level)
        log_table.add_row("Type", settings.logger.type)

        if settings.logger.type == "file":
            path = getattr(settings.logger, "path", None)
            if path:
                log_table.add_row("Path", str(path))
            else:
                log_table.add_row("Path", "[red]Not configured[/red]")

        console.print(Panel(log_table, border_style="blue"))

    # OTEL Configuration
    if settings.otel and settings.otel.enabled:
        otel_table = Table(
            title="OpenTelemetry Configuration", show_header=False, box=None
        )
        otel_table.add_column("Setting", style="cyan")
        otel_table.add_column("Value")

        otel_table.add_row("Enabled", "[green]Yes[/green]")

        exporters = settings.otel.exporters or []
        if exporters:
            exporter_info = []
            for e in exporters:
                exp_type = getattr(e, "type", "unknown")
                if exp_type == "otlp":
                    endpoint = getattr(e, "endpoint", None)
                    if endpoint:
                        exporter_info.append(f"OTLP ({endpoint})")
                    else:
                        exporter_info.append("OTLP [red](no endpoint)[/red]")
                else:
                    exporter_info.append(exp_type)
            otel_table.add_row("Exporters", ", ".join(exporter_info))
        else:
            otel_table.add_row("Exporters", "[yellow]None configured[/yellow]")

        console.print(Panel(otel_table, border_style="blue"))

    # Generate and display suggestions
    suggestions = _generate_suggestions(
        config_status, secrets_status, providers, servers, commands, settings
    )

    if suggestions:
        console.print("\n[bold]Actionable Suggestions:[/bold]\n")
        for i, suggestion in enumerate(suggestions, 1):
            console.print(f"{i}. {suggestion}")
        console.print()
    else:
        console.print(
            "\n[green]✓ All checks passed! Your configuration looks good.[/green]\n"
        )

    # Quick start tips
    console.print(
        Panel(
            "[bold]Quick Start Commands:[/bold]\n\n"
            "• Create config: [cyan]mcp-agent init[/cyan]\n"
            "• Add API key: [cyan]mcp-agent keys set <provider> <key>[/cyan]\n"
            "• Add server: [cyan]mcp-agent server add recipe filesystem[/cyan]\n"
            "• Start chat: [cyan]mcp-agent chat --model anthropic.haiku[/cyan]\n"
            "• Run agent: [cyan]mcp-agent dev start --script main.py[/cyan]",
            title="Getting Started",
            border_style="dim",
        )
    )
