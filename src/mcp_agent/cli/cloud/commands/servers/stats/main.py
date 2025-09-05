import json
from typing import Optional

import typer
import yaml
from rich.panel import Panel

from mcp_agent.cli.exceptions import CLIError
from ..utils import (
    setup_authenticated_client,
    validate_output_format, 
    resolve_server,
    handle_server_api_errors,
    get_server_name,
)
from mcp_agent.cli.utils.ux import console, print_info


@handle_server_api_errors
def get_server_stats(
    id_or_url: str = typer.Argument(..., help="Server ID or URL to get statistics for"),
    range: Optional[str] = typer.Option("24h", "--range", "-r", help="Time range for statistics (1h|24h|7d)"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """Get statistics for a specific MCP Server."""
    valid_ranges = ["1h", "24h", "7d"]
    if range not in valid_ranges:
        raise CLIError(f"Invalid range '{range}'. Valid options are: {', '.join(valid_ranges)}")
    
    validate_output_format(format)
    client = setup_authenticated_client()
    server = resolve_server(client, id_or_url)
    server_name = get_server_name(server)
    print_server_stats(server_name, id_or_url, range, format)


def print_server_stats(server_name: str, server_id: str, time_range: str, output_format: str) -> None:
    """Print server statistics information."""
    
    if output_format == "json":
        _print_stats_json(server_name, server_id, time_range)
    elif output_format == "yaml":
        _print_stats_yaml(server_name, server_id, time_range)
    else:
        _print_stats_text(server_name, server_id, time_range)


def _print_stats_json(server_name: str, server_id: str, time_range: str) -> None:
    """Print server statistics in JSON format."""
    stats_data = {
        "server": {
            "id": server_id,
            "name": server_name
        },
        "time_range": time_range,
        "status": "not_implemented",
        "message": "Statistics API not yet implemented",
        "available_metrics": [
            "request_count",
            "response_time",
            "error_rate", 
            "resource_usage",
            "uptime"
        ]
    }
    print(json.dumps(stats_data, indent=2))


def _print_stats_yaml(server_name: str, server_id: str, time_range: str) -> None:
    """Print server statistics in YAML format."""
    stats_data = {
        "server": {
            "id": server_id,
            "name": server_name
        },
        "time_range": time_range,
        "status": "not_implemented",
        "message": "Statistics API not yet implemented",
        "available_metrics": [
            "request_count",
            "response_time", 
            "error_rate",
            "resource_usage",
            "uptime"
        ]
    }
    print(yaml.dump(stats_data, default_flow_style=False))


def _print_stats_text(server_name: str, server_id: str, time_range: str) -> None:
    """Print server statistics in text format."""
    console.print(
        Panel(
            f"Server: [cyan]{server_name}[/cyan]\n"
            f"ID: [cyan]{server_id}[/cyan]\n"
            f"Time Range: [cyan]{time_range}[/cyan]\n\n"
            f"[yellow]📊 Statistics API not yet implemented[/yellow]\n\n"
            f"This command is ready to display server statistics including:\n"
            f"• Request count and rate\n"
            f"• Response times and latency\n" 
            f"• Error rates and status codes\n"
            f"• Resource usage metrics\n"
            f"• Uptime and availability\n\n"
            f"The backend API endpoint will need to be implemented to provide\n"
            f"detailed server performance and usage statistics.",
            title="Server Statistics",
            border_style="blue",
            expand=False,
        )
    )
    
    print_info(
        "💡 To implement full statistics functionality, add a stats endpoint "
        "to the MCP App API service that returns server metrics for the specified time range."
    )