"""Workflow runs command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.table import Table

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings
from mcp_agent.mcp.gen_client import gen_client
from ...utils import (
    setup_authenticated_client,
    validate_output_format,
    resolve_server,
)
from mcp_agent.cli.utils.ux import console, print_info


async def _list_workflow_runs_async(
    server_id_or_url: str, limit: Optional[int], status: Optional[str], format: str
) -> None:
    """List workflow runs using MCP tool calls to a deployed server."""
    if server_id_or_url.startswith(("http://", "https://")):
        server_url = server_id_or_url
    else:
        client = setup_authenticated_client()
        server = resolve_server(client, server_id_or_url)

        if hasattr(server, "appServerInfo") and server.appServerInfo:
            server_url = server.appServerInfo.serverUrl
        else:
            raise CLIError(
                f"Server '{server_id_or_url}' is not deployed or has no server URL"
            )

        if not server_url:
            raise CLIError(f"No server URL found for server '{server_id_or_url}'")

    quiet_settings = Settings(logger=LoggerSettings(level="error"))
    app = MCPApp(name="workflows_cli", settings=quiet_settings)

    try:
        async with app.run() as workflow_app:
            context = workflow_app.context

            sse_url = (
                f"{server_url}/sse" if not server_url.endswith("/sse") else server_url
            )
            context.server_registry.registry["workflow_server"] = MCPServerSettings(
                name="workflow_server",
                description=f"Deployed MCP server {server_url}",
                url=sse_url,
                transport="sse",
            )

            async with gen_client(
                "workflow_server", server_registry=context.server_registry
            ) as client:
                result = await client.call_tool("workflows-runs-list", {})

                workflows_data = result.content[0].text if result.content else []
                if isinstance(workflows_data, str):
                    workflows_data = json.loads(workflows_data)

                if not workflows_data:
                    workflows_data = []

                # Apply filtering
                workflows = workflows_data
                if status:
                    status_filter = _get_status_filter(status)
                    workflows = [w for w in workflows if _matches_status(w, status_filter)]

                if limit:
                    workflows = workflows[:limit]

                if format == "json":
                    _print_workflows_json(workflows)
                elif format == "yaml":
                    _print_workflows_yaml(workflows)
                else:
                    _print_workflows_text(workflows, status, server_id_or_url)

    except Exception as e:
        raise CLIError(
            f"Error listing workflow runs for server {server_id_or_url}: {str(e)}"
        ) from e


def list_workflow_runs(
    server_id_or_url: str = typer.Argument(
        ..., help="Server ID, app config ID, or server URL to list workflow runs for"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Maximum number of results to return"
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filter by status: running|failed|timed_out|canceled|terminated|completed|continued",
    ),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """List workflow runs for an MCP Server.

    Examples:

        mcp-agent cloud workflows runs app_abc123

        mcp-agent cloud workflows runs https://server.example.com --status running

        mcp-agent cloud workflows runs apcnf_xyz789 --limit 10 --format json
    """
    validate_output_format(format)
    run_async(_list_workflow_runs_async(server_id_or_url, limit, status, format))


def _get_status_filter(status: str) -> str:
    """Convert status string to normalized status."""
    status_map = {
        "running": "running",
        "failed": "failed",
        "timed_out": "timed_out",
        "timeout": "timed_out",  # alias
        "canceled": "canceled",
        "cancelled": "canceled",  # alias
        "terminated": "terminated",
        "completed": "completed",
        "continued": "continued",
        "continued_as_new": "continued",
    }
    normalized_status = status_map.get(status.lower())
    if not normalized_status:
        valid_statuses = "running|failed|timed_out|timeout|canceled|cancelled|terminated|completed|continued|continued_as_new"
        raise typer.BadParameter(
            f"Invalid status '{status}'. Valid options: {valid_statuses}"
        )
    return normalized_status


def _matches_status(workflow: dict, status_filter: str) -> bool:
    """Check if workflow matches the status filter."""
    workflow_status = workflow.get("execution_status", "")
    if isinstance(workflow_status, str):
        return status_filter.lower() in workflow_status.lower()
    return False


def _print_workflows_text(workflows, status_filter, server_id_or_url):
    """Print workflows in text format."""
    server_name = server_id_or_url

    console.print(
        f"\n[bold blue]📊 Workflow Runs for Server: {server_name}[/bold blue]"
    )

    if not workflows:
        print_info("No workflow runs found for this server.")
        return

    console.print(f"\nFound {len(workflows)} workflow run(s):")

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Workflow ID", style="cyan", width=20)
    table.add_column("Name", style="green", width=20)
    table.add_column("Status", style="yellow", width=15)
    table.add_column("Run ID", style="dim", width=15)
    table.add_column("Created", style="dim", width=20)
    table.add_column("Principal", style="dim", width=15)

    for workflow in workflows:
        # Handle both dict and object formats
        if isinstance(workflow, dict):
            workflow_id = workflow.get("workflow_id", "N/A")
            name = workflow.get("name", "N/A")
            execution_status = workflow.get("execution_status", "N/A")
            run_id = workflow.get("run_id", "N/A")
            created_at = workflow.get("created_at", "N/A")
            principal_id = workflow.get("principal_id", "N/A")
        else:
            workflow_id = getattr(workflow, "workflow_id", "N/A")
            name = getattr(workflow, "name", "N/A")
            execution_status = getattr(workflow, "execution_status", "N/A")
            run_id = getattr(workflow, "run_id", "N/A")
            created_at = getattr(workflow, "created_at", "N/A")
            principal_id = getattr(workflow, "principal_id", "N/A")
        
        status_display = _get_status_display(execution_status)
        
        # Handle created_at formatting
        if created_at and created_at != "N/A":
            if hasattr(created_at, "strftime"):
                created_display = created_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Try to parse ISO string
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    created_display = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    created_display = str(created_at)
        else:
            created_display = "N/A"
        
        run_id_display = _truncate_string(str(run_id) if run_id else "N/A", 15)

        table.add_row(
            _truncate_string(str(workflow_id) if workflow_id else "N/A", 20),
            _truncate_string(str(name) if name else "N/A", 20),
            status_display,
            run_id_display,
            created_display,
            _truncate_string(str(principal_id) if principal_id else "N/A", 15),
        )

    console.print(table)

    if status_filter:
        console.print(f"\n[dim]Filtered by status: {status_filter}[/dim]")


def _print_workflows_json(workflows):
    """Print workflows in JSON format."""
    workflows_data = [_workflow_to_dict(workflow) for workflow in workflows]
    print(json.dumps({"workflow_runs": workflows_data}, indent=2, default=str))


def _print_workflows_yaml(workflows):
    """Print workflows in YAML format."""
    workflows_data = [_workflow_to_dict(workflow) for workflow in workflows]
    print(yaml.dump({"workflow_runs": workflows_data}, default_flow_style=False))


def _workflow_to_dict(workflow):
    """Convert workflow dict to standardized dictionary format."""
    # If it's already a dict, just return it
    if isinstance(workflow, dict):
        return workflow
    
    # Otherwise convert from object attributes
    return {
        "workflow_id": getattr(workflow, "workflow_id", None),
        "run_id": getattr(workflow, "run_id", None),
        "name": getattr(workflow, "name", None),
        "created_at": getattr(workflow, "created_at", None).isoformat() if getattr(workflow, "created_at", None) else None,
        "principal_id": getattr(workflow, "principal_id", None),
        "execution_status": getattr(workflow, "execution_status", None).value if getattr(workflow, "execution_status", None) else None,
    }


def _truncate_string(text: str, max_length: int) -> str:
    """Truncate string to max_length, adding ellipsis if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _get_status_display(status):
    """Convert status to display string with emoji."""
    if not status:
        return "❓ Unknown"
    
    # Convert to string for comparison
    status_str = str(status).lower()
    
    if "running" in status_str:
        return "[green]🟢 Running[/green]"
    elif "completed" in status_str:
        return "[blue]✅ Completed[/blue]"
    elif "failed" in status_str or "error" in status_str:
        return "[red]❌ Failed[/red]"
    elif "cancel" in status_str:
        return "[yellow]🟡 Canceled[/yellow]"
    elif "terminat" in status_str:
        return "[red]🔴 Terminated[/red]"
    elif "timeout" in status_str or "timed_out" in status_str:
        return "[orange]⏰ Timed Out[/orange]"
    elif "continued" in status_str:
        return "[purple]🔄 Continued[/purple]"
    else:
        return f"❓ {status}"
