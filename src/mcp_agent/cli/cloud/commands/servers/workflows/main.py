import json
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.table import Table

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp
from ..utils import (
    setup_authenticated_client,
    validate_output_format, 
    resolve_server,
    handle_server_api_errors,
    get_server_name,
    get_server_id,
)
from mcp_agent.cli.utils.ux import console, print_info


@handle_server_api_errors
def list_server_workflows(
    id_or_url: str = typer.Argument(..., help="Server ID or URL to list workflows for"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum number of workflows to return"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by workflow status (running|paused|failed|completed)"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """List workflows for a specific MCP Server."""
    if status:
        valid_statuses = ["running", "paused", "failed", "completed"]
        if status not in valid_statuses:
            raise CLIError(f"Invalid status '{status}'. Valid options are: {', '.join(valid_statuses)}")

    validate_output_format(format)
    client = setup_authenticated_client()
    server = resolve_server(client, id_or_url)
    
    server_type = "Deployed Server" if isinstance(server, MCPApp) else "Configured Server"
    server_name = get_server_name(server)
    server_id = get_server_id(server)
    
    print_server_info(server_name, server_type, server_id)
    
    # Show that this feature requires backend API support
    print_workflows_unavailable(status, limit, format)


def print_server_info(server_name: str, server_type: str, server_id: str) -> None:
    """Print server information header."""
    console.print(
        Panel(
            f"Server: [cyan]{server_name}[/cyan]\n"
            f"Type: [cyan]{server_type}[/cyan]\n"
            f"ID: [cyan]{server_id}[/cyan]",
            title="Server Information",
            border_style="blue",
            expand=False,
        )
    )


def print_workflows_unavailable(status_filter: Optional[str], limit: Optional[int], output_format: str) -> None:
    """Print message that workflow listing is not available without backend support."""
    
    if output_format == "json":
        _print_workflows_unavailable_json(status_filter, limit)
    elif output_format == "yaml":
        _print_workflows_unavailable_yaml(status_filter, limit)
    else:
        _print_workflows_unavailable_text(status_filter, limit)


def _print_workflows_unavailable_json(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflow unavailability message in JSON format."""
    error_data = {
        "error": "workflow_listing_unavailable",
        "message": "Workflow listing by server requires backend API support",
        "detail": "No workflow listing API exists. Only individual workflow lookup via workflow ID is supported.",
        "requested_filters": {
            "status": status_filter,
            "limit": limit
        },
        "alternative": "Use 'mcp-agent cloud workflow status --id <workflow-id>' for individual workflow details"
    }
    print(json.dumps(error_data, indent=2))


def _print_workflows_unavailable_yaml(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflow unavailability message in YAML format."""
    error_data = {
        "error": "workflow_listing_unavailable",
        "message": "Workflow listing by server requires backend API support",
        "detail": "No workflow listing API exists. Only individual workflow lookup via workflow ID is supported.",
        "requested_filters": {
            "status": status_filter,
            "limit": limit
        },
        "alternative": "Use 'mcp-agent cloud workflow status --id <workflow-id>' for individual workflow details"
    }
    print(yaml.dump(error_data, default_flow_style=False))


def _print_workflows_unavailable_text(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflow unavailability message in text format."""
    console.print(
        Panel(
            f"[red]❌ Workflow listing unavailable[/red]\n\n"
            f"Requested filters:\n"
            f"• Status: [cyan]{status_filter or 'All'}[/cyan]\n"
            f"• Limit: [cyan]{limit or 'No limit'}[/cyan]\n\n"
            f"[yellow]Issue:[/yellow] No workflow listing API exists in the backend.\n"
            f"Only individual workflow lookup is supported.\n\n"
            f"[blue]Alternative:[/blue] Use individual workflow commands:\n"
            f"• [cyan]mcp-agent cloud workflow status --id <workflow-id>[/cyan]\n\n"
            f"[dim]To implement this feature, the backend would need:\n"
            f"• A workflow listing API endpoint\n"
            f"• Server/app filtering support in workflow queries[/dim]",
            title="Workflow Listing Not Available",
            border_style="red",
            expand=False,
        )
    )
    
    print_info(
        "💡 To implement full workflow listing functionality, extend the ListWorkflowsRequest "
        "in the workflow API to filter by AppSpecifier (app_id or app_config_id)."
    )