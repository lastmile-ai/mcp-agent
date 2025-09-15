"""
Build preflight: checks keys, servers, commands; writes manifest.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import socket
from typing import Dict, Any, Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.config import get_settings, Settings


app = typer.Typer(help="Preflight and bundle prep for deployment")
console = Console()


def _check_command(cmd: str) -> tuple[bool, str]:
    """Check if a command is available and return version if possible."""
    parts = cmd.split()
    exe = parts[0]

    # Check if command exists
    if not shutil.which(exe):
        return False, "Not found"

    # Try to get version for common commands
    version = "Found"
    try:
        if exe in ["node", "npm", "npx", "python", "python3", "pip", "uv", "uvx"]:
            result = subprocess.run(
                [exe, "--version"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                version = result.stdout.strip()
    except Exception:
        pass

    return True, version


def _check_url(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Check if a URL is reachable and return response time."""
    try:
        from urllib.parse import urlparse
        import time

        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if not host:
            return False, "Invalid URL"

        start = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = time.time() - start
            return True, f"{elapsed * 1000:.0f}ms"
    except socket.timeout:
        return False, "Timeout"
    except socket.gaierror:
        return False, "DNS error"
    except Exception as e:
        return False, str(e)[:20]


def _check_environment_vars(settings: Settings) -> Dict[str, Any]:
    """Check for environment variables that might override settings."""
    env_vars = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
        "AZURE_API_KEY": bool(os.getenv("AZURE_API_KEY")),
        "AWS_ACCESS_KEY_ID": bool(os.getenv("AWS_ACCESS_KEY_ID")),
        "AWS_SECRET_ACCESS_KEY": bool(os.getenv("AWS_SECRET_ACCESS_KEY")),
    }
    return env_vars


def _check_file_permissions(path: Path) -> Dict[str, Any]:
    """Check file permissions for sensitive files."""
    result = {
        "exists": path.exists(),
        "readable": False,
        "writable": False,
        "permissions": None,
        "secure": False,
    }

    if path.exists():
        result["readable"] = os.access(path, os.R_OK)
        result["writable"] = os.access(path, os.W_OK)

        # Check if permissions are too open for secrets file
        if "secrets" in path.name:
            stat_info = path.stat()
            mode = stat_info.st_mode
            # Check if others have read access
            result["secure"] = not bool(mode & 0o004)
            result["permissions"] = oct(mode)[-3:]

    return result


def _check_dependencies() -> Dict[str, Any]:
    """Check Python dependencies and versions."""
    deps = {}

    # Check core dependencies
    required_packages = [
        "mcp",
        "typer",
        "rich",
        "pydantic",
        "httpx",
        "yaml",
    ]

    for package in required_packages:
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            deps[package] = {"installed": True, "version": version}
        except ImportError:
            deps[package] = {"installed": False, "version": None}

    # Check Python version
    deps["python"] = {
        "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "supported": sys.version_info >= (3, 10),
    }

    return deps


def _check_network_connectivity() -> Dict[str, bool]:
    """Check connectivity to common services."""
    endpoints = {
        "internet": ("8.8.8.8", 53),  # Google DNS
        "openai": ("api.openai.com", 443),
        "anthropic": ("api.anthropic.com", 443),
        "google": ("generativelanguage.googleapis.com", 443),
        "github": ("api.github.com", 443),
    }

    results = {}
    for name, (host, port) in endpoints.items():
        try:
            with socket.create_connection((host, port), timeout=2):
                results[name] = True
        except Exception:
            results[name] = False

    return results


def _validate_config_schema(settings: Settings) -> List[str]:
    """Validate configuration against expected schema."""
    warnings = []

    # Check for required fields
    if not settings.execution_engine:
        warnings.append("No execution_engine specified (defaulting to asyncio)")

    if settings.logger and settings.logger.type == "file":
        if not settings.logger.path_settings:
            warnings.append("Logger type is 'file' but no path_settings configured")

    # Check MCP servers
    if settings.mcp and settings.mcp.servers:
        for name, server in settings.mcp.servers.items():
            if server.transport == "stdio" and not server.command:
                warnings.append(f"Server '{name}' missing command")
            elif server.transport in ["http", "sse"] and not server.url:
                warnings.append(f"Server '{name}' missing URL")

    return warnings


@app.callback(invoke_without_command=True)
def build(
    check_only: bool = typer.Option(
        False, "--check-only", help="Run checks without creating manifest"
    ),
    fix: bool = typer.Option(False, "--fix", help="Attempt to fix minor issues"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output directory for manifest"
    ),
) -> None:
    """Run comprehensive preflight checks and generate build manifest."""

    console.print("\n[bold cyan]🔍 MCP-Agent Build Preflight Checks[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running preflight checks...", total=None)

        settings = get_settings()
        ok = True
        from datetime import datetime, timezone

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "providers": {},
            "servers": {},
            "environment": {},
            "files": {},
            "dependencies": {},
            "network": {},
            "warnings": [],
        }

        # Check provider configurations
        progress.update(task, description="Checking provider configurations...")
        provs = [
            ("openai", getattr(settings, "openai", None), "api_key"),
            ("anthropic", getattr(settings, "anthropic", None), "api_key"),
            ("google", getattr(settings, "google", None), "api_key"),
            ("azure", getattr(settings, "azure", None), "api_key"),
            ("bedrock", getattr(settings, "bedrock", None), "aws_access_key_id"),
        ]

        for name, obj, keyfield in provs:
            has_config = bool(getattr(obj, keyfield, None)) if obj else False
            has_env = bool(os.getenv(f"{name.upper()}_API_KEY")) or (
                name == "bedrock" and bool(os.getenv("AWS_ACCESS_KEY_ID"))
            )

            report["providers"][name] = {
                "configured": has_config,
                "env_var": has_env,
                "available": has_config or has_env,
            }

        # Check environment variables
        progress.update(task, description="Checking environment variables...")
        report["environment"] = _check_environment_vars(settings)

        # Check file permissions
        progress.update(task, description="Checking file permissions...")
        config_file = Path("mcp_agent.config.yaml")
        secrets_file = Path("mcp_agent.secrets.yaml")

        report["files"]["config"] = _check_file_permissions(config_file)
        report["files"]["secrets"] = _check_file_permissions(secrets_file)

        # Warn about insecure secrets file
        if secrets_file.exists() and not report["files"]["secrets"]["secure"]:
            report["warnings"].append(
                f"Secrets file has unsafe permissions: {report['files']['secrets']['permissions']}"
            )

        # Check MCP servers
        progress.update(task, description="Checking MCP servers...")
        servers = (settings.mcp.servers if settings.mcp else {}) or {}

        for name, s in servers.items():
            status = {"transport": s.transport}

            if s.transport == "stdio":
                status["command"] = s.command
                found, version = _check_command(s.command)
                status["command_found"] = found
                status["version"] = version

                if not found:
                    ok = False
                    report["warnings"].append(
                        f"Server '{name}' command not found: {s.command}"
                    )
            else:
                status["url"] = s.url
                reachable, response = _check_url(s.url)
                status["reachable"] = reachable
                status["response_time"] = response

                if not reachable and verbose:
                    report["warnings"].append(
                        f"Server '{name}' not reachable: {response}"
                    )

            # Check server-specific environment variables
            if s.env:
                status["env_vars"] = {}
                for key in s.env.keys():
                    status["env_vars"][key] = bool(os.getenv(key))

            report["servers"][name] = status

        # Check dependencies
        if verbose:
            progress.update(task, description="Checking dependencies...")
            report["dependencies"] = _check_dependencies()

            # Check if all required dependencies are installed
            for pkg, info in report["dependencies"].items():
                if pkg != "python" and not info.get("installed"):
                    report["warnings"].append(f"Missing dependency: {pkg}")

        # Check network connectivity
        if verbose:
            progress.update(task, description="Checking network connectivity...")
            report["network"] = _check_network_connectivity()

        # Validate configuration schema
        progress.update(task, description="Validating configuration...")
        schema_warnings = _validate_config_schema(settings)
        report["warnings"].extend(schema_warnings)

    # Display results
    console.print("\n[bold]Preflight Check Results[/bold]\n")

    # Providers table
    provider_table = Table(
        title="Provider Status", show_header=True, header_style="cyan"
    )
    provider_table.add_column("Provider", style="green")
    provider_table.add_column("Config", justify="center")
    provider_table.add_column("Env Var", justify="center")
    provider_table.add_column("Status", justify="center")

    for name, info in report["providers"].items():
        config = "✅" if info["configured"] else "❌"
        env = "✅" if info["env_var"] else "❌"
        status = (
            "[green]Ready[/green]"
            if info["available"]
            else "[yellow]Not configured[/yellow]"
        )
        provider_table.add_row(name.capitalize(), config, env, status)

    console.print(provider_table)
    console.print()

    # Servers table
    if report["servers"]:
        server_table = Table(
            title="MCP Server Status", show_header=True, header_style="cyan"
        )
        server_table.add_column("Server", style="green")
        server_table.add_column("Transport")
        server_table.add_column("Target")
        server_table.add_column("Status", justify="center")

        for name, info in report["servers"].items():
            if info["transport"] == "stdio":
                target = info.get("command", "N/A")
                if info["command_found"]:
                    status = f"[green]✅ {info['version']}[/green]"
                else:
                    status = "[red]❌ Not found[/red]"
            else:
                target = info.get("url", "N/A")[:40]
                if info.get("reachable"):
                    status = f"[green]✅ {info['response_time']}[/green]"
                else:
                    status = (
                        f"[yellow]⚠️  {info.get('response_time', 'Unknown')}[/yellow]"
                    )

            server_table.add_row(name, info["transport"], target, status)

        console.print(server_table)
        console.print()
    else:
        console.print("[yellow]No MCP servers found in configuration[/yellow]")
        console.print()

    # Show warnings
    if report["warnings"]:
        console.print(
            Panel(
                "\n".join(f"• {w}" for w in report["warnings"]),
                title="[yellow]Warnings[/yellow]",
                border_style="yellow",
            )
        )
        console.print()

    # Write manifest
    if not check_only:
        out_dir = output or Path(".mcp-agent")
        out_dir.mkdir(exist_ok=True, parents=True)
        manifest = out_dir / "manifest.json"
        manifest.write_text(json.dumps(report, indent=2))
        console.print(f"[green]✅[/green] Wrote manifest: [cyan]{manifest}[/cyan]")

    # Fix suggestions
    if fix and not ok:
        console.print("\n[bold yellow]🔧 Fix Suggestions:[/bold yellow]\n")

        for name, st in report["servers"].items():
            if st.get("transport") == "stdio" and not st.get("command_found"):
                cmd = st.get("command", "")
                if "npx" in cmd:
                    console.print(
                        "• Install npm: [cyan]brew install node[/cyan] (macOS) or [cyan]apt install nodejs[/cyan]"
                    )
                elif "uvx" in cmd:
                    console.print(
                        "• Install uv: [cyan]pip install uv[/cyan] or [cyan]brew install uv[/cyan]"
                    )
                else:
                    console.print(f"• Ensure '{cmd}' is installed and on PATH")

        if not any(p["available"] for p in report["providers"].values()):
            console.print(
                "• Add API keys to mcp_agent.secrets.yaml or set environment variables"
            )

    # Final status
    if ok:
        console.print("\n[green bold]✅ Preflight checks passed![/green bold]")
    else:
        console.print("\n[red bold]❌ Preflight checks failed[/red bold]")
        if not check_only:
            raise typer.Exit(1)


@app.command()
def validate(
    config_file: Path = typer.Option(Path("mcp_agent.config.yaml"), "--config", "-c"),
    secrets_file: Path = typer.Option(
        Path("mcp_agent.secrets.yaml"), "--secrets", "-s"
    ),
) -> None:
    """Validate configuration files against schema."""
    console.print("\n[bold]Validating configuration files...[/bold]\n")

    errors = []

    # Check if files exist
    if not config_file.exists():
        errors.append(f"Config file not found: {config_file}")

    if not secrets_file.exists():
        console.print(
            f"[yellow]Warning:[/yellow] Secrets file not found: {secrets_file}"
        )

    if errors:
        for error in errors:
            console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1)

    # Load and validate
    try:
        settings = get_settings()
        warnings = _validate_config_schema(settings)

        if warnings:
            console.print("[yellow]Validation warnings:[/yellow]")
            for warning in warnings:
                console.print(f"  • {warning}")
        else:
            console.print("[green]✅ Configuration is valid[/green]")

    except Exception as e:
        console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(1)
