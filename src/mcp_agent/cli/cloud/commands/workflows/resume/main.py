"""Workflow resume command implementation."""

import json
from typing import Optional

import typer

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings
from mcp_agent.mcp.gen_client import gen_client
from ...utils import setup_authenticated_client, resolve_server, handle_server_api_errors


async def _signal_workflow_async(
    server_id_or_url: str,
    run_id: str,
    signal_name: str = "resume",
    payload: Optional[str] = None
) -> None:
    """Send a signal to a workflow using MCP tool calls to a deployed server."""
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
            
            sse_url = f"{server_url.rstrip('/')}/sse" if not server_url.endswith('/sse') else server_url
            context.server_registry.registry["workflow_server"] = MCPServerSettings(
                name="workflow_server",
                description=f"Deployed MCP server {server_url}",
                url=sse_url,
                transport="sse"
            )
            
            async with gen_client("workflow_server", server_registry=context.server_registry) as client:
                tool_params = {"run_id": run_id, "signal_name": signal_name}
                if payload:
                    tool_params["payload"] = payload
                
                result = await client.call_tool("workflows-resume", tool_params)
                
                success = result.content[0].text if result.content else False
                if isinstance(success, str):
                    success = success.lower() == 'true'
                
                if success:
                    action_past = "resumed" if signal_name == "resume" else "suspended" if signal_name == "suspend" else f"signaled ({signal_name})"
                    action_color = "green" if signal_name == "resume" else "yellow" if signal_name == "suspend" else "blue"
                    action_icon = "✓" if signal_name == "resume" else "⏸" if signal_name == "suspend" else "📡"
                    console.print(f"[{action_color}]{action_icon}[/{action_color}] Successfully {action_past} workflow")
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                else:
                    raise CLIError(f"Failed to {signal_name} workflow with run ID {run_id}")
                    
    except Exception as e:
        raise CLIError(f"Error {signal_name}ing workflow with run ID {run_id}: {str(e)}") from e


@handle_server_api_errors
def resume_workflow(
    server_id_or_url: str = typer.Argument(..., help="Server ID or URL hosting the workflow"),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to resume"),
    payload: Optional[str] = typer.Option(None, "--payload", help="JSON or text payload to pass to resumed workflow"),
) -> None:
    """Resume a suspended workflow execution.
    
    Resumes execution of a previously suspended workflow. Optionally accepts
    a payload (JSON or text) to pass data to the resumed workflow.
    
    Examples:
        mcp-agent cloud workflows resume app_abc123 run_xyz789
        mcp-agent cloud workflows resume https://server.example.com run_xyz789 --payload '{"data": "value"}'
        mcp-agent cloud workflows resume app_abc123 run_xyz789 --payload "simple text"
    """
    if payload:
        try:
            json.loads(payload)
            console.print("[dim]Resuming with JSON payload...[/dim]")
        except json.JSONDecodeError:
            console.print("[dim]Resuming with text payload...[/dim]")

    run_async(_signal_workflow_async(server_id_or_url, run_id, "resume", payload))


@handle_server_api_errors
def suspend_workflow(
    server_id_or_url: str = typer.Argument(..., help="Server ID or URL hosting the workflow"),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to suspend"),
    payload: Optional[str] = typer.Option(None, "--payload", help="JSON or text payload to pass to suspended workflow"),
) -> None:
    """Suspend a workflow execution.
    
    Temporarily pauses a workflow execution, which can later be resumed.
    Optionally accepts a payload (JSON or text) to pass data to the suspended workflow.
    
    Examples:
        mcp-agent cloud workflows suspend app_abc123 run_xyz789
        mcp-agent cloud workflows suspend https://server.example.com run_xyz789 --payload '{"reason": "maintenance"}'
        mcp-agent cloud workflows suspend app_abc123 run_xyz789 --payload "paused for review"
    """
    if payload:
        try:
            json.loads(payload)
            console.print("[dim]Suspending with JSON payload...[/dim]")
        except json.JSONDecodeError:
            console.print("[dim]Suspending with text payload...[/dim]")

    run_async(_signal_workflow_async(server_id_or_url, run_id, "suspend", payload))
