"""
Keys management with provider-specific features and validation.
"""

from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

import typer
import yaml
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn


app = typer.Typer(help="Manage provider API keys")
console = Console()


# Comprehensive provider configuration
PROVIDERS = {
    "openai": {
        "env": "OPENAI_API_KEY",
        "name": "OpenAI",
        "pattern": r"^sk-[A-Za-z0-9_-]+$",
        "format": "sk-XXXXXXXX... (48 chars)",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "test_endpoint": "https://api.openai.com/v1/models",
        "docs": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "name": "Anthropic",
        "pattern": r"^sk-ant-[a-zA-Z0-9_-]{80,}$",
        "format": "sk-ant-XXXXXXXX... (80+ chars)",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        "test_endpoint": "https://api.anthropic.com/v1/models",
        "docs": "https://console.anthropic.com/settings/keys",
    },
    "google": {
        "env": "GOOGLE_API_KEY",
        "name": "Google",
        "pattern": r"^[a-zA-Z0-9\-_]{39}$",
        "format": "XXXXXXXX... (39 chars)",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
        "test_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        "docs": "https://makersuite.google.com/app/apikey",
    },
    "azure": {
        "env": "AZURE_API_KEY",
        "name": "Azure OpenAI",
        "pattern": r"^[a-f0-9]{32,}$",
        "format": "32+ hex characters",
        "additional_env": {
            "AZURE_BASE_URL": "Azure endpoint URL",
            "AZURE_API_VERSION": "API version (e.g., 2024-02-01)",
            "AZURE_DEPLOYMENT_NAME": "Deployment name",
        },
        "docs": "https://portal.azure.com/#blade/HubsExtension/BrowseResource/resourceType/Microsoft.CognitiveServices%2Faccounts",
    },
    "bedrock": {
        "env": "AWS_ACCESS_KEY_ID",
        "name": "AWS Bedrock",
        "pattern": r"^[A-Z0-9]{20}$",
        "format": "20 uppercase alphanumeric",
        "additional_env": {
            "AWS_SECRET_ACCESS_KEY": "Secret access key",
            "AWS_REGION": "AWS region (e.g., us-east-1)",
        },
        "models": [
            "anthropic.claude-3-sonnet",
            "anthropic.claude-3-haiku",
            "amazon.titan",
        ],
        "docs": "https://console.aws.amazon.com/iam/home#/security_credentials",
    },
}


def _validate_key(provider: str, key: str) -> Tuple[bool, str]:
    """Validate API key format for a provider."""
    if provider not in PROVIDERS:
        return False, "Unknown provider"

    config = PROVIDERS[provider]
    pattern = config.get("pattern")

    if not pattern:
        # No validation pattern available
        return True, "No validation available"

    if re.match(pattern, key):
        return True, "Valid format"
    else:
        return (
            False,
            f"Invalid format. Expected: {config.get('format', 'Unknown format')}",
        )


def _mask_key(key: str, show_chars: int = 4) -> str:
    """Mask an API key, showing only last few characters."""
    if not key:
        return ""
    if len(key) <= show_chars:
        return "***"
    return f"***{key[-show_chars:]}"


async def _test_key(provider: str, key: str) -> Tuple[bool, str]:
    """Test if an API key works by making a simple request."""
    import httpx

    config = PROVIDERS.get(provider)
    if not config or not config.get("test_endpoint"):
        return False, "No test endpoint available"

    try:
        headers = {}

        if provider == "openai":
            headers = {"Authorization": f"Bearer {key}"}
        elif provider == "anthropic":
            headers = {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            }
        elif provider == "google":
            # Google uses query parameter
            endpoint = f"{config['test_endpoint']}?key={key}"
            headers = {}
        else:
            return False, "Test not implemented for this provider"

        async with httpx.AsyncClient() as client:
            if provider == "google":
                response = await client.get(endpoint, timeout=5)
            else:
                response = await client.get(
                    config["test_endpoint"], headers=headers, timeout=5
                )

            if response.status_code in [200, 401, 403]:
                if response.status_code == 200:
                    return True, "Key is valid"
                else:
                    return False, f"Invalid key (HTTP {response.status_code})"
            else:
                return False, f"Unexpected response (HTTP {response.status_code})"

    except Exception as e:
        return False, f"Connection error: {str(e)[:50]}"


@app.command("show")
def show(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
    test: bool = typer.Option(False, "--test", "-t", help="Test API keys"),
) -> None:
    """Show configured API keys and their status."""
    from mcp_agent.config import get_settings

    console.print("\n[bold cyan]🔑 API Key Status[/bold cyan]\n")

    settings = get_settings()

    table = Table(show_header=True, header_style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Status", justify="center")
    table.add_column("Source")
    table.add_column("Key (masked)")

    if verbose:
        table.add_column("Format")

    if test:
        table.add_column("Test", justify="center")

    for provider_key, config in PROVIDERS.items():
        env_var = config["env"]
        provider_name = config["name"]

        # Check environment variable
        env_val = os.environ.get(env_var)

        # Check config/secrets
        provider_settings = getattr(settings, provider_key, None)
        cfg_val = (
            getattr(provider_settings, "api_key", None) if provider_settings else None
        )

        # Determine active key and source
        active_key = cfg_val or env_val
        source = "secrets" if cfg_val else ("env" if env_val else "none")

        # Status
        if active_key:
            valid, message = _validate_key(provider_key, active_key)
            if valid:
                status = "[green]✅[/green]"
            else:
                status = "[yellow]⚠️[/yellow]"
        else:
            status = "[red]❌[/red]"

        # Masked key
        masked = _mask_key(active_key) if active_key else "-"

        row = [provider_name, status, source, masked]

        if verbose:
            row.append(config.get("format", "N/A"))

        if test and active_key:
            # Test the key
            import asyncio

            success, test_msg = asyncio.run(_test_key(provider_key, active_key))
            if success:
                row.append("[green]✅[/green]")
            else:
                row.append("[red]❌[/red]")
        elif test:
            row.append("-")

        table.add_row(*row)

    console.print(table)

    # Show additional environment variables if verbose
    if verbose:
        additional_vars = []
        for provider_key, config in PROVIDERS.items():
            if "additional_env" in config:
                for var, desc in config["additional_env"].items():
                    val = os.environ.get(var)
                    if val:
                        additional_vars.append(
                            f"  • {var}: {_mask_key(val, 8)} ({desc})"
                        )

        if additional_vars:
            console.print("\n[bold]Additional Environment Variables:[/bold]")
            for var in additional_vars:
                console.print(var)

    # Show help
    console.print(
        "\n[dim]Use [cyan]mcp-agent keys set <provider>[/cyan] to configure keys[/dim]"
    )
    console.print(
        "[dim]Use [cyan]mcp-agent keys test[/cyan] to validate all keys[/dim]"
    )


@app.command("set")
def set_key(
    provider: str = typer.Argument(..., help="Provider name"),
    key: Optional[str] = typer.Option(
        None, "--key", "-k", help="API key (will prompt if not provided)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip validation"),
    env_only: bool = typer.Option(
        False, "--env-only", help="Set in environment only, not secrets file"
    ),
) -> None:
    """Set API key for a provider."""
    import yaml
    from mcp_agent.config import Settings

    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Available providers: {', '.join(PROVIDERS.keys())}")
        raise typer.Exit(1)

    config = PROVIDERS[provider]
    provider_name = config["name"]
    env_var = config["env"]

    console.print(f"\n[bold]Setting {provider_name} API Key[/bold]\n")

    # Get key if not provided
    if not key:
        console.print(f"Format: {config.get('format', 'Any format')}")
        if config.get("docs"):
            console.print(f"Get your key at: [cyan]{config['docs']}[/cyan]")

        key = Prompt.ask(f"\n{provider_name} API key", password=True)

    if not key:
        console.print("[yellow]No key provided[/yellow]")
        raise typer.Exit(0)

    # Validate format
    if not force:
        valid, message = _validate_key(provider, key)
        if not valid:
            console.print(f"[red]Validation failed: {message}[/red]")
            if not Confirm.ask("Continue anyway?", default=False):
                raise typer.Exit(1)

    # Set in environment
    os.environ[env_var] = key
    console.print(f"[green]✅[/green] Set {env_var} in environment")

    # Handle additional environment variables
    if "additional_env" in config:
        console.print(
            f"\n[bold]{provider_name} requires additional configuration:[/bold]"
        )
        for var, desc in config["additional_env"].items():
            current = os.environ.get(var, "")
            value = Prompt.ask(f"{desc} ({var})", default=current)
            if value:
                os.environ[var] = value

    # Save to secrets file unless env-only
    if not env_only:
        sec_path = Settings.find_secrets()
        if not sec_path:
            # Create in current directory
            sec_path = Path.cwd() / "mcp_agent.secrets.yaml"
            data = {}
        else:
            try:
                data = yaml.safe_load(sec_path.read_text()) or {}
            except Exception:
                data = {}

        # Update provider section
        if provider not in data:
            data[provider] = {}
        data[provider]["api_key"] = key

        # Add additional config if needed
        if "additional_env" in config:
            for var, _ in config["additional_env"].items():
                val = os.environ.get(var)
                if val:
                    # Map env var to config key
                    config_key = (
                        var.lower()
                        .replace(f"{provider.upper()}_", "")
                        .replace("_", "_")
                    )
                    data[provider][config_key] = val

        # Write secrets file
        try:
            sec_path.write_text(yaml.safe_dump(data, sort_keys=False))
            console.print(f"[green]✅[/green] Saved to {sec_path}")

            # Set secure permissions
            try:
                import stat

                os.chmod(sec_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
                console.print("[dim]Set secure permissions (600)[/dim]")
            except Exception:
                pass

        except Exception as e:
            console.print(f"[red]Failed to write secrets: {e}[/red]")

    # Test the key
    if not force:
        console.print("\n[dim]Testing key...[/dim]")
        import asyncio

        success, message = asyncio.run(_test_key(provider, key))
        if success:
            console.print(f"[green]✅ {message}[/green]")
        else:
            console.print(f"[yellow]⚠️  {message}[/yellow]")

    console.print(f"\n[green bold]✅ {provider_name} key configured![/green bold]")


@app.command("unset")
def unset(
    provider: str = typer.Argument(..., help="Provider name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove API key for a provider."""
    import yaml
    from mcp_agent.config import Settings

    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)

    config = PROVIDERS[provider]
    provider_name = config["name"]
    env_var = config["env"]

    if not force:
        if not Confirm.ask(f"Remove {provider_name} API key?", default=False):
            raise typer.Exit(0)

    # Remove from environment
    if env_var in os.environ:
        os.environ.pop(env_var)
        console.print(f"[green]✅[/green] Removed {env_var} from environment")

    # Remove additional env vars
    if "additional_env" in config:
        for var in config["additional_env"]:
            if var in os.environ:
                os.environ.pop(var)
                console.print(f"[green]✅[/green] Removed {var} from environment")

    # Remove from secrets file
    sec_path = Settings.find_secrets()
    if sec_path and sec_path.exists():
        try:
            data = yaml.safe_load(sec_path.read_text()) or {}
            if provider in data:
                data.pop(provider)
                sec_path.write_text(yaml.safe_dump(data, sort_keys=False))
                console.print(f"[green]✅[/green] Removed from {sec_path}")
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not update secrets file: {e}[/yellow]"
            )

    console.print(f"\n[green]✅ {provider_name} key removed[/green]")


@app.command("test")
def test(
    provider: Optional[str] = typer.Argument(None, help="Provider to test (or all)"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed results"
    ),
) -> None:
    """Test API keys by making validation requests."""
    from mcp_agent.config import get_settings
    import asyncio

    console.print("\n[bold cyan]🧪 Testing API Keys[/bold cyan]\n")

    settings = get_settings()

    # Determine which providers to test
    if provider:
        if provider not in PROVIDERS:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            raise typer.Exit(1)
        providers_to_test = [provider]
    else:
        providers_to_test = list(PROVIDERS.keys())

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for provider_key in providers_to_test:
            config = PROVIDERS[provider_key]
            provider_name = config["name"]

            task = progress.add_task(f"Testing {provider_name}...", total=None)

            # Get the key
            env_var = config["env"]
            env_val = os.environ.get(env_var)
            provider_settings = getattr(settings, provider_key, None)
            cfg_val = (
                getattr(provider_settings, "api_key", None)
                if provider_settings
                else None
            )
            active_key = cfg_val or env_val

            if not active_key:
                progress.update(
                    task,
                    description=f"[yellow]⏭️  {provider_name}: Not configured[/yellow]",
                )
                results.append((provider_name, "Not configured", None))
                continue

            # Validate format
            valid, format_msg = _validate_key(provider_key, active_key)

            # Test the key
            success, test_msg = asyncio.run(_test_key(provider_key, active_key))

            if success:
                progress.update(
                    task, description=f"[green]✅ {provider_name}: Valid[/green]"
                )
                results.append((provider_name, "Valid", test_msg))
            else:
                progress.update(
                    task, description=f"[red]❌ {provider_name}: {test_msg}[/red]"
                )
                results.append((provider_name, "Invalid", test_msg))

    # Show summary
    console.print("\n[bold]Test Results:[/bold]\n")

    summary_table = Table(show_header=True, header_style="cyan")
    summary_table.add_column("Provider", style="green")
    summary_table.add_column("Status", justify="center")
    if verbose:
        summary_table.add_column("Details")

    for provider_name, status, details in results:
        if status == "Valid":
            status_icon = "[green]✅ Valid[/green]"
        elif status == "Invalid":
            status_icon = "[red]❌ Invalid[/red]"
        else:
            status_icon = "[yellow]⏭️  Skipped[/yellow]"

        row = [provider_name, status_icon]
        if verbose and details:
            row.append(details)

        summary_table.add_row(*row)

    console.print(summary_table)

    # Count results
    valid_count = sum(1 for _, status, _ in results if status == "Valid")
    invalid_count = sum(1 for _, status, _ in results if status == "Invalid")
    skipped_count = sum(1 for _, status, _ in results if status == "Not configured")

    console.print(
        f"\n[bold]Summary:[/bold] {valid_count} valid, {invalid_count} invalid, {skipped_count} not configured"
    )

    if invalid_count > 0:
        console.print(
            "\n[dim]Use [cyan]mcp-agent keys set <provider>[/cyan] to fix invalid keys[/dim]"
        )


@app.command("rotate")
def rotate(
    provider: str = typer.Argument(..., help="Provider name"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Backup old key"),
) -> None:
    """Rotate API key for a provider (backup old, set new)."""

    from mcp_agent.config import get_settings

    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)

    config = PROVIDERS[provider]
    provider_name = config["name"]

    console.print(f"\n[bold cyan]🔄 Rotating {provider_name} API Key[/bold cyan]\n")

    # Get current key
    settings = get_settings()
    provider_settings = getattr(settings, provider, None)
    old_key = getattr(provider_settings, "api_key", None) if provider_settings else None

    if not old_key:
        old_key = os.environ.get(config["env"])

    if old_key and backup:
        # Backup old key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = Path.cwd() / f".mcp-agent/backup_{provider}_{timestamp}.txt"
        backup_file.parent.mkdir(exist_ok=True, parents=True)

        backup_data = {
            "provider": provider,
            "timestamp": timestamp,
            "key": old_key,
            "masked": _mask_key(old_key, 8),
        }

        backup_file.write_text(json.dumps(backup_data, indent=2))
        console.print(f"[green]✅[/green] Backed up old key to {backup_file}")

        # Set secure permissions
        try:
            import stat

            os.chmod(backup_file, stat.S_IRUSR | stat.S_IWUSR)  # 600
        except Exception:
            pass

    # Get new key
    console.print(f"\nEnter new {provider_name} API key")
    console.print(f"Format: {config.get('format', 'Any format')}")

    new_key = Prompt.ask("New API key", password=True)

    if not new_key:
        console.print("[yellow]No key provided[/yellow]")
        raise typer.Exit(0)

    # Set new key
    set_key(provider=provider, key=new_key, force=False, env_only=False)

    console.print(
        f"\n[green bold]✅ {provider_name} key rotated successfully![/green bold]"
    )

    if backup and old_key:
        console.print(
            f"[dim]Old key backed up to .mcp-agent/backup_{provider}_{timestamp}.txt[/dim]"
        )


@app.command("export")
def export(
    output: Path = typer.Option(Path("keys.env"), "--output", "-o", help="Output file"),
    format: str = typer.Option("env", "--format", "-f", help="Format: env|json|yaml"),
) -> None:
    """Export all configured keys to a file."""
    from mcp_agent.config import get_settings

    console.print("\n[bold]Exporting API Keys[/bold]\n")

    settings = get_settings()
    keys = {}

    # Collect all keys
    for provider_key, config in PROVIDERS.items():
        env_var = config["env"]

        # Check config/secrets
        provider_settings = getattr(settings, provider_key, None)
        cfg_val = (
            getattr(provider_settings, "api_key", None) if provider_settings else None
        )

        # Check environment
        env_val = os.environ.get(env_var)

        active_key = cfg_val or env_val
        if active_key:
            keys[env_var] = active_key

            # Include additional env vars
            if "additional_env" in config:
                for var in config["additional_env"]:
                    val = os.environ.get(var)
                    if val:
                        keys[var] = val

    if not keys:
        console.print("[yellow]No keys to export[/yellow]")
        raise typer.Exit(0)

    # Format output
    if format == "env":
        content = "\n".join(f'{k}="{v}"' for k, v in keys.items())
    elif format == "json":
        content = json.dumps(keys, indent=2)
    elif format == "yaml":
        content = yaml.safe_dump(keys, sort_keys=False)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)

    # Write file
    output.write_text(content)
    console.print(f"[green]✅[/green] Exported {len(keys)} keys to {output}")

    # Set secure permissions
    try:
        import stat

        os.chmod(output, stat.S_IRUSR | stat.S_IWUSR)  # 600
        console.print("[dim]Set secure permissions (600)[/dim]")
    except Exception:
        pass

    console.print(
        "\n[yellow]⚠️  Warning: This file contains sensitive API keys![/yellow]"
    )
    console.print("[dim]Keep it secure and don't commit to version control[/dim]")
