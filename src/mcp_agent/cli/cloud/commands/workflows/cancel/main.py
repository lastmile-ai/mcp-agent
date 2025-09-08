"""Workflow cancel command implementation."""

from typing import Optional

import typer

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings
from mcp_agent.mcp.gen_client import gen_client
from ...utils import setup_authenticated_client, resolve_server, handle_server_api_errors


async def _cancel_workflow_async(
    server_id_or_url: str,
    run_id: str,
    reason: Optional[str] = None
) -> None:
    """Cancel a workflow using MCP tool calls to a deployed server."""
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
                tool_params = {"run_id": run_id}
                
                result = await client.call_tool("workflows-cancel", tool_params)
                
                success = result.content[0].text if result.content else False
                if isinstance(success, str):
                    success = success.lower() == 'true'
                
                if success:
                    console.print("[yellow]⚠[/yellow] Successfully cancelled workflow")
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                    if reason:
                        console.print(f"  Reason: [dim]{reason}[/dim]")
                else:
                    raise CLIError(f"Failed to cancel workflow with run ID {run_id}")
                    
    except Exception as e:
        raise CLIError(f"Error cancelling workflow with run ID {run_id}: {str(e)}") from e


@handle_server_api_errors
def cancel_workflow(
    server_id_or_url: str = typer.Argument(..., help="Server ID or URL hosting the workflow"),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to cancel"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Optional reason for cancellation"),
) -> None:
    """Cancel a workflow execution.
    
    Permanently stops a workflow execution. Unlike suspend, a cancelled workflow
    cannot be resumed and will be marked as cancelled.
    
    Examples:
        mcp-agent cloud workflows cancel app_abc123 run_xyz789
        mcp-agent cloud workflows cancel https://server.example.com run_xyz789 --reason "User requested cancellation"
    """
    run_async(_cancel_workflow_async(server_id_or_url, run_id, reason))
