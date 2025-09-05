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
    print_workflows_placeholder(status, limit, format)


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


def print_workflows_placeholder(status_filter: Optional[str], limit: Optional[int], output_format: str) -> None:
    """Print workflows information placeholder."""
    
    if output_format == "json":
        _print_workflows_json(status_filter, limit)
    elif output_format == "yaml":
        _print_workflows_yaml(status_filter, limit)
    else:
        _print_workflows_text(status_filter, limit)


def _print_workflows_json(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflows in JSON format."""
    workflows_data = {
        "status": "not_implemented",
        "message": "Workflow listing by server not yet implemented",
        "filters": {
            "status": status_filter,
            "limit": limit
        },
        "sample_workflows": [
            {
                "workflow_id": "wf_example123",
                "name": "data-processor",
                "status": "running",
                "created_at": "2024-01-15T10:30:00Z",
                "run_id": "run_abc456"
            },
            {
                "workflow_id": "wf_example456", 
                "name": "email-sender",
                "status": "completed",
                "created_at": "2024-01-15T09:15:00Z",
                "run_id": "run_def789"
            }
        ],
        "available_fields": [
            "workflow_id",
            "name",
            "status",
            "created_at",
            "run_id",
            "duration",
            "performance_metrics"
        ]
    }
    print(json.dumps(workflows_data, indent=2))


def _print_workflows_yaml(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflows in YAML format."""
    workflows_data = {
        "status": "not_implemented",
        "message": "Workflow listing by server not yet implemented",
        "filters": {
            "status": status_filter,
            "limit": limit
        },
        "sample_workflows": [
            {
                "workflow_id": "wf_example123",
                "name": "data-processor",
                "status": "running",
                "created_at": "2024-01-15T10:30:00Z",
                "run_id": "run_abc456"
            },
            {
                "workflow_id": "wf_example456",
                "name": "email-sender", 
                "status": "completed",
                "created_at": "2024-01-15T09:15:00Z",
                "run_id": "run_def789"
            }
        ],
        "available_fields": [
            "workflow_id",
            "name",
            "status",
            "created_at",
            "run_id",
            "duration",
            "performance_metrics"
        ]
    }
    print(yaml.dump(workflows_data, default_flow_style=False))


def _print_workflows_text(status_filter: Optional[str], limit: Optional[int]) -> None:
    """Print workflows in text format."""
    table = Table(title="Server Workflows (Placeholder)")
    table.add_column("Workflow ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Created", style="magenta")
    table.add_column("Run ID", style="blue")
    table.add_row(
        "wf_example123",
        "data-processor",
        "🔄 Running",
        "2024-01-15 10:30:00",
        "run_abc456"
    )
    table.add_row(
        "wf_example456",
        "email-sender",
        "✅ Completed",
        "2024-01-15 09:15:00", 
        "run_def789"
    )

    console.print("\n")
    console.print(table)
    
    console.print(
        Panel(
            f"[yellow]🚧 Workflow listing by server not yet implemented[/yellow]\n\n"
            f"Applied filters:\n"
            f"• Status: [cyan]{status_filter or 'All'}[/cyan]\n"
            f"• Limit: [cyan]{limit or 'No limit'}[/cyan]\n\n"
            f"This command is ready to display workflows running on this server including:\n"
            f"• Workflow ID and execution details\n"
            f"• Workflow name and type\n"
            f"• Current execution status\n"
            f"• Creation timestamp and run ID\n"
            f"• Duration and performance metrics\n\n"
            f"The backend API needs to be extended to support listing workflows\n"
            f"by server/app ID using the AppSpecifier from the workflow proto.",
            title="Implementation Status",
            border_style="yellow",
            expand=False,
        )
    )
    
    print_info(
        "💡 To implement full workflow listing functionality, extend the ListWorkflowsRequest "
        "in the workflow API to filter by AppSpecifier (app_id or app_config_id)."
    )