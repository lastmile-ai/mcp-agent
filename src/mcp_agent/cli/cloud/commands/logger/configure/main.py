"""Configure OTEL endpoint and headers for logging."""

from pathlib import Path
from typing import Optional

import httpx
import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import print_error

console = Console()


def configure_logger(
    endpoint: Optional[str] = typer.Argument(
        None,
        help="OTEL endpoint URL for log collection",
    ),
    headers: Optional[str] = typer.Option(
        None,
        "--headers",
        "-h",
        help="Additional headers in key=value,key2=value2 format",
    ),
    test: bool = typer.Option(
        False,
        "--test",
        help="Test the connection without saving configuration",
    ),
) -> None:
    """Configure OTEL endpoint and headers for log collection.

    This command allows you to configure the OpenTelemetry endpoint and headers
    that will be used for collecting logs from your deployed MCP apps.

    Examples:
        mcp-agent cloud logger configure https://otel.example.com:4318/v1/logs
        mcp-agent cloud logger configure https://otel.example.com --headers "Authorization=Bearer token,X-Custom=value"
        mcp-agent cloud logger configure --test  # Test current configuration
    """
    if not endpoint and not test:
        print_error("Must specify endpoint or use --test")
        raise typer.Exit(1)

    config_path = _find_config_file()

    if test:
        if config_path and config_path.exists():
            config = _load_config(config_path)
            otel_config = config.get("otel", {})
            endpoint = otel_config.get("endpoint")
            headers_dict = otel_config.get("headers", {})
        else:
            console.print(
                "[yellow]No configuration file found. Use --endpoint to set up OTEL configuration.[/yellow]"
            )
            raise typer.Exit(1)
    else:
        headers_dict = {}
        if headers:
            try:
                for header_pair in headers.split(","):
                    key, value = header_pair.strip().split("=", 1)
                    headers_dict[key.strip()] = value.strip()
            except ValueError:
                print_error("Headers must be in format 'key=value,key2=value2'")
                raise typer.Exit(1)

    if endpoint:
        console.print(f"[blue]Testing connection to {endpoint}...[/blue]")

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    endpoint.replace("/v1/logs", "/health")
                    if "/v1/logs" in endpoint
                    else f"{endpoint}/health",
                    headers=headers_dict,
                )

                if response.status_code in [
                    200,
                    404,
                ]:  # 404 is fine, means endpoint exists
                    console.print("[green]✓ Connection successful[/green]")
                else:
                    console.print(
                        f"[yellow]⚠ Got status {response.status_code}, but endpoint is reachable[/yellow]"
                    )

        except httpx.RequestError as e:
            print_error(f"✗ Connection failed: {e}")
            if not test:
                console.print(
                    "[yellow]Configuration will be saved anyway. Check your endpoint URL and network connection.[/yellow]"
                )

    if not test:
        if not config_path:
            config_path = Path.cwd() / "mcp_agent.config.yaml"

        config = _load_config(config_path) if config_path.exists() else {}

        if "otel" not in config:
            config["otel"] = {}

        config["otel"]["endpoint"] = endpoint
        config["otel"]["headers"] = headers_dict

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            console.print(
                Panel(
                    f"[green]✓ OTEL configuration saved to {config_path}[/green]\n\n"
                    f"Endpoint: {endpoint}\n"
                    f"Headers: {len(headers_dict)} configured"
                    + (f" ({', '.join(headers_dict.keys())})" if headers_dict else ""),
                    title="Configuration Saved",
                    border_style="green",
                )
            )

        except Exception as e:
            raise CLIError(f"Error saving configuration: {e}")


def _find_config_file() -> Optional[Path]:
    """Find mcp_agent.config.yaml by searching upward from current directory."""
    current = Path.cwd()
    while current != current.parent:
        config_path = current / "mcp_agent.config.yaml"
        if config_path.exists():
            return config_path
        current = current.parent
    return None


def _load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise CLIError(f"Failed to load config from {config_path}: {e}")
