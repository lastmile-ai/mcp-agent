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
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings
from mcp_agent.mcp.gen_client import gen_client
from ...servers.utils import setup_authenticated_client, resolve_server, handle_server_api_errors


async def _describe_workflow_async(
    server_id_or_url: str,
    run_id: str,
    format: str = "text"
) -> None:
    """Describe a workflow using MCP tool calls to a deployed server."""
    if server_id_or_url.startswith(('http://', 'https://')):
        server_url = server_id_or_url
    else:
        client = setup_authenticated_client()
        server = resolve_server(client, server_id_or_url)
        
        if hasattr(server, 'appServerInfo') and server.appServerInfo:
            server_url = server.appServerInfo.serverUrl
        else:
            raise CLIError(f"Server '{server_id_or_url}' is not deployed or has no server URL")
        
        if not server_url:
            raise CLIError(f"No server URL found for server '{server_id_or_url}'")
    
    quiet_settings = Settings(logger=LoggerSettings(level="error"))
    app = MCPApp(name="workflows_cli", settings=quiet_settings)
    
    try:
        async with app.run() as workflow_app:
            context = workflow_app.context

            sse_url = f"{server_url}/sse" if not server_url.endswith('/sse') else server_url
            context.server_registry.registry["workflow_server"] = MCPServerSettings(
                name="workflow_server",
                description=f"Deployed MCP server {server_url}",
                url=sse_url,
                transport="sse"
            )
            
            async with gen_client("workflow_server", server_registry=context.server_registry) as client:
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


@handle_server_api_errors
def describe_workflow(
    server_id_or_url: str = typer.Argument(..., help="Server ID or URL hosting the workflow"),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to describe"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """Describe a workflow execution (alias: status).
    
    Shows detailed information about a workflow execution including its current status,
    creation time, and other metadata.
    
    Examples:
        mcp-agent cloud workflows describe app_abc123 run_xyz789
        mcp-agent cloud workflows describe https://server.example.com run_xyz789 --format json
    """
    if format not in ["text", "json", "yaml"]:
        console.print("[red]Error: --format must be 'text', 'json', or 'yaml'[/red]")
        raise typer.Exit(6)

    run_async(_describe_workflow_async(server_id_or_url, run_id, format))


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