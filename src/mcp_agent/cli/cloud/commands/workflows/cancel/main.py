"""Workflow cancel command implementation."""

import json
from typing import Optional

import typer

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.mcp.gen_client import gen_client


async def _cancel_workflow_async(
    run_id: str,
    reason: Optional[str] = None
) -> None:
    """Cancel a workflow using MCP tool calls."""
    # Create a temporary MCP app to connect to temporal server
    app = MCPApp(name="workflows_cli")
    
    try:
        async with app.run() as workflow_app:
            async with gen_client("temporal", server_registry=workflow_app.context.server_registry) as client:
                tool_params = {"run_id": run_id}
                
                result = await client.call_tool("workflows-cancel", tool_params)
                
                success = result.content[0].text if result.content else False
                if isinstance(success, str):
                    success = success.lower() == 'true'
                
                if success:
                    console.print(f"[yellow]⚠[/yellow] Successfully cancelled workflow")
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                    if reason:
                        console.print(f"  Reason: [dim]{reason}[/dim]")
                else:
                    raise CLIError(f"Failed to cancel workflow with run ID {run_id}")
                    
    except Exception as e:
        raise CLIError(f"Error cancelling workflow with run ID {run_id}: {str(e)}") from e


def cancel_workflow(
    run_id: str = typer.Argument(..., help="Run ID of the workflow to cancel"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Optional reason for cancellation"),
) -> None:
    """Cancel a workflow execution.
    
    Permanently stops a workflow execution. Unlike suspend, a cancelled workflow
    cannot be resumed and will be marked as cancelled.
    
    Examples:
        mcp-agent cloud workflows cancel run_abc123
        mcp-agent cloud workflows cancel run_abc123 --reason "User requested cancellation"
    """
    run_async(_cancel_workflow_async(run_id, reason))