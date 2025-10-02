import json
from typing import Optional, Union

import typer
import yaml
from rich.panel import Panel

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppConfiguration
from ...utils import (
    setup_authenticated_client,
    validate_output_format,
    resolve_server,
    handle_server_api_errors,
    clean_server_status,
)
from mcp_agent.cli.utils.ux import console


@handle_server_api_errors
def describe_server(
    id_or_url: str = typer.Argument(
        ..., help="App ID, server URL, or app name to describe"
    ),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """Describe a specific MCP Server."""
    validate_output_format(format)
    client = setup_authenticated_client()
    server = resolve_server(client, id_or_url)
    print_server_description(server, format)


def print_server_description(
    server: Union[MCPApp, MCPAppConfiguration], output_format: str = "text"
) -> None:
    """Print detailed description information for a server."""

    valid_formats = ["text", "json", "yaml"]
    if output_format not in valid_formats:
        raise CLIError(
            f"Invalid format '{output_format}'. Valid options are: {', '.join(valid_formats)}"
        )

    if output_format == "json":
        _print_server_json(server)
    elif output_format == "yaml":
        _print_server_yaml(server)
    else:
        _print_server_text(server)


def _print_server_json(server: Union[MCPApp, MCPAppConfiguration]) -> None:
    """Print server in JSON format."""
    server_data = _server_to_dict(server)
    print(json.dumps(server_data, indent=2, default=str))


def _print_server_yaml(server: Union[MCPApp, MCPAppConfiguration]) -> None:
    """Print server in YAML format."""
    server_data = _server_to_dict(server)
    print(yaml.dump(server_data, default_flow_style=False))


def _server_to_dict(server: Union[MCPApp, MCPAppConfiguration]) -> dict:
    """Convert server to dictionary."""
    if isinstance(server, MCPApp):
        server_type = "deployed"
        server_id = server.appId
        server_name = server.name
        server_description = server.description
        created_at = server.createdAt
        server_info = server.appServerInfo
        underlying_app = None
    else:
        server_type = "configured"
        server_id = server.appConfigurationId
        server_name = server.app.name if server.app else "Unnamed"
        server_description = server.app.description if server.app else None
        created_at = server.createdAt
        server_info = server.appServerInfo
        underlying_app = (
            {"app_id": server.app.appId, "name": server.app.name}
            if server.app
            else None
        )

    status_raw = server_info.status if server_info else "APP_SERVER_STATUS_OFFLINE"
    server_url = server_info.serverUrl if server_info else None

    data = {
        "id": server_id,
        "name": server_name,
        "type": server_type,
        "status": clean_server_status(status_raw),
        "server_url": server_url,
        "description": server_description,
        "created_at": created_at.isoformat() if created_at else None,
    }

    if underlying_app:
        data["underlying_app"] = underlying_app

    return data


def _print_server_text(server: Union[MCPApp, MCPAppConfiguration]) -> None:
    """Print server in text format."""
    if isinstance(server, MCPApp):
        server_type = "Deployed Server"
        server_id = server.appId
        server_name = server.name
        server_description = server.description
        created_at = server.createdAt
        server_info = server.appServerInfo
    else:
        server_type = "Configured Server"
        server_id = server.appConfigurationId
        server_name = server.app.name if server.app else "Unnamed"
        server_description = server.app.description if server.app else None
        created_at = server.createdAt
        server_info = server.appServerInfo

    status_text = "❓ Unknown"
    server_url = "N/A"

    if server_info:
        status_text = _server_status_text(server_info.status)
        server_url = server_info.serverUrl
    content_lines = [
        f"Name: [cyan]{server_name}[/cyan]",
        f"Type: [cyan]{server_type}[/cyan]",
        f"ID: [cyan]{server_id}[/cyan]",
        f"Status: {status_text}",
        f"Server URL: [cyan]{server_url}[/cyan]",
    ]

    if server_description:
        content_lines.append(f"Description: [cyan]{server_description}[/cyan]")

    if created_at:
        content_lines.append(
            f"Created: [cyan]{created_at.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]"
        )

    if isinstance(server, MCPAppConfiguration) and server.app:
        content_lines.extend(
            [
                "",
                "[bold]Underlying App:[/bold]",
                f"  App ID: [cyan]{server.app.appId}[/cyan]",
                f"  App Name: [cyan]{server.app.name}[/cyan]",
            ]
        )

    console.print(
        Panel(
            "\n".join(content_lines),
            title="Server Description",
            border_style="blue",
            expand=False,
        )
    )


def _server_status_text(status: str) -> str:
    """Convert server status code to emoji and text."""
    if status == "APP_SERVER_STATUS_ONLINE":
        return "[green]🟢 Active[/green]"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return "[red]🔴 Offline[/red]"
    else:
        return "❓ Unknown"
