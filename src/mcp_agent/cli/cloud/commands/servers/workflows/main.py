"""Server workflows command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.table import Table

from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.mcp_app.api_client import WorkflowExecutionStatus
from ...utils import (
    setup_authenticated_client,
    validate_output_format,
    handle_server_api_errors,
    resolve_server,
)
from mcp_agent.cli.utils.ux import console, print_info


@handle_server_api_errors
def list_workflows_for_server(
    app_id_or_config_id: str = typer.Argument(..., help="App ID (app_xxx) or app config ID (apcnf_xxx) to list workflows for"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Maximum number of results to return"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status: running|failed|timed_out|canceled|terminated|completed|continued"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """List workflows for an MCP Server.
    
    Examples:
    
        mcp-agent cloud servers workflows app_abc123
        
        mcp-agent cloud servers workflows apcnf_xyz789 --status running
        
        mcp-agent cloud servers workflows app_abc123 --limit 10 --format json
    """
    validate_output_format(format)
    client = setup_authenticated_client()
    
    server = None
    try:
        server = resolve_server(client, app_id_or_config_id)
    except Exception:
        pass
    
    max_results = limit or 100
    
    status_filter = None
    if status:
        status_map = {
            "running": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING,
            "failed": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_FAILED,
            "timed_out": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TIMED_OUT,
            "timeout": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TIMED_OUT,  # alias
            "canceled": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED,
            "cancelled": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED,  # alias
            "terminated": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TERMINATED,
            "completed": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED,
            "continued": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW,
            "continued_as_new": WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW,
        }
        status_filter = status_map.get(status.lower())
        if not status_filter:
            valid_statuses = "running|failed|timed_out|timeout|canceled|cancelled|terminated|completed|continued|continued_as_new"
            raise typer.BadParameter(f"Invalid status '{status}'. Valid options: {valid_statuses}")

    async def list_workflows_async():
        return await client.list_workflows(
            app_id_or_config_id=app_id_or_config_id,
            max_results=max_results
        )

    response = run_async(list_workflows_async())
    workflows = response.workflows or []
    
    if status_filter:
        workflows = [w for w in workflows if w.execution_status == status_filter]
    
    if format == "json":
        _print_workflows_json(workflows)
    elif format == "yaml":
        _print_workflows_yaml(workflows)
    else:
        _print_workflows_text(workflows, server, status, app_id_or_config_id)


def _print_workflows_text(workflows, server, status_filter, app_id_or_config_id):
    """Print workflows in text format."""
    if server and hasattr(server, 'name') and server.name:
        server_name = server.name
    else:
        server_name = app_id_or_config_id
    
    console.print(f"\n[bold blue]📊 Workflows for Server: {server_name}[/bold blue]")
    
    if not workflows:
        print_info("No workflows found for this server.")
        return
    
    console.print(f"\nFound {len(workflows)} workflow(s):")
    
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Workflow ID", style="cyan", width=20)
    table.add_column("Name", style="green", width=20)
    table.add_column("Status", style="yellow", width=15)
    table.add_column("Run ID", style="dim", width=15)
    table.add_column("Created", style="dim", width=20)
    table.add_column("Principal", style="dim", width=15)
    
    for workflow in workflows:
        status_display = _get_status_display(workflow.execution_status)
        created_display = workflow.created_at.strftime('%Y-%m-%d %H:%M:%S') if workflow.created_at else "N/A"
        run_id_display = _truncate_string(workflow.run_id or "N/A", 15)
        
        table.add_row(
            _truncate_string(workflow.workflow_id, 20),
            _truncate_string(workflow.name, 20),
            status_display,
            run_id_display,
            created_display,
            _truncate_string(workflow.principal_id, 15),
        )
    
    console.print(table)
    
    if status_filter:
        console.print(f"\n[dim]Filtered by status: {status_filter}[/dim]")


def _print_workflows_json(workflows):
    """Print workflows in JSON format."""
    workflows_data = [_workflow_to_dict(workflow) for workflow in workflows]
    print(json.dumps({"workflows": workflows_data}, indent=2, default=str))


def _print_workflows_yaml(workflows):
    """Print workflows in YAML format."""
    workflows_data = [_workflow_to_dict(workflow) for workflow in workflows]
    print(yaml.dump({"workflows": workflows_data}, default_flow_style=False))


def _workflow_to_dict(workflow):
    """Convert WorkflowInfo to dictionary."""
    return {
        "workflow_id": workflow.workflow_id,
        "run_id": workflow.run_id,
        "name": workflow.name,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "principal_id": workflow.principal_id,
        "execution_status": workflow.execution_status.value if workflow.execution_status else None,
    }


def _truncate_string(text: str, max_length: int) -> str:
    """Truncate string to max_length, adding ellipsis if truncated."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def _get_status_display(status):
    """Convert WorkflowExecutionStatus to display string with emoji."""
    if not status:
        return "❓ Unknown"
    
    status_map = {
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING: "[green]🟢 Running[/green]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED: "[blue]✅ Completed[/blue]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_FAILED: "[red]❌ Failed[/red]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED: "[yellow]🟡 Canceled[/yellow]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TERMINATED: "[red]🔴 Terminated[/red]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TIMED_OUT: "[orange]⏰ Timed Out[/orange]",
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW: "[purple]🔄 Continued[/purple]",
    }
    
    return status_map.get(status, "❓ Unknown")