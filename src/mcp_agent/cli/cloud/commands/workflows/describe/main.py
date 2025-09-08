"""Workflow describe command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.panel import Panel

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.mcp.gen_client import gen_client


async def _describe_workflow_async(
    run_id: str,
    format: str = "text"
) -> None:
    """Describe a workflow using MCP tool calls."""
    # Create a temporary MCP app to connect to temporal server
    app = MCPApp(name="workflows_cli")
    
    try:
        async with app.run() as workflow_app:
            async with gen_client("temporal", server_registry=workflow_app.context.server_registry) as client:
                result = await client.call_tool("workflows-get_status", {
                    "run_id": run_id
                })
                
                workflow_status = result.content[0].text if result.content else {}
                if isinstance(workflow_status, str):
                    workflow_status = json.loads(workflow_status)
                
                if not workflow_status:
                    raise CLIError(f"Workflow with run ID '{run_id}' not found.")

                if format == "json":
                    print(json.dumps(workflow_status, indent=2))
                elif format == "yaml":
                    print(yaml.dump(workflow_status, default_flow_style=False))
                else:  # text format
                    print_workflow_status(workflow_status)
                    
    except Exception as e:
        raise CLIError(f"Error describing workflow with run ID {run_id}: {str(e)}") from e


def describe_workflow(
    run_id: str = typer.Argument(..., help="Run ID of the workflow to describe"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """Describe a workflow execution (alias: status).
    
    Shows detailed information about a workflow execution including its current status,
    creation time, and other metadata.
    """
    if format not in ["text", "json", "yaml"]:
        console.print("[red]Error: --format must be 'text', 'json', or 'yaml'[/red]")
        raise typer.Exit(6)

    run_async(_describe_workflow_async(run_id, format))


def print_workflow_status(workflow_status: dict) -> None:
    """Print workflow status information in text format."""
    name = workflow_status.get("name", "N/A")
    workflow_id = workflow_status.get("workflow_id", workflow_status.get("workflowId", "N/A"))
    run_id = workflow_status.get("run_id", workflow_status.get("runId", "N/A"))
    status = workflow_status.get("status", "N/A")
    
    created_at = workflow_status.get("created_at", workflow_status.get("createdAt", "N/A"))
    if created_at != "N/A" and isinstance(created_at, str):
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            created_at = created_dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass  # Keep original format if parsing fails
    
    console.print(
        Panel(
            f"Name: [cyan]{name}[/cyan]\n"
            f"Workflow ID: [cyan]{workflow_id}[/cyan]\n"
            f"Run ID: [cyan]{run_id}[/cyan]\n"
            f"Created: [cyan]{created_at}[/cyan]\n"
            f"Status: [cyan]{_format_status(status)}[/cyan]",
            title="Workflow",
            border_style="blue",
            expand=False,
        )
    )


def _format_status(status: str) -> str:
    """Format the execution status text."""
    status_lower = str(status).lower()
    
    if "running" in status_lower:
        return "🔄 Running"
    elif "failed" in status_lower or "error" in status_lower:
        return "❌ Failed"
    elif "timeout" in status_lower or "timed_out" in status_lower:
        return "⌛ Timed Out"
    elif "cancel" in status_lower:
        return "🚫 Cancelled"
    elif "terminat" in status_lower:
        return "🛑 Terminated"
    elif "complet" in status_lower:
        return "✅ Completed"
    elif "continued" in status_lower:
        return "🔁 Continued as New"
    else:
        return f"❓ {status}"