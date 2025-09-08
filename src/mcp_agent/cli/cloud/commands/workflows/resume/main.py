"""Workflow resume command implementation."""

import json
from typing import Optional

import typer

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.mcp.gen_client import gen_client


async def _resume_workflow_async(
    run_id: str,
    payload: Optional[str] = None
) -> None:
    """Resume a workflow using MCP tool calls."""
    # Create a temporary MCP app to connect to temporal server
    app = MCPApp(name="workflows_cli")
    
    try:
        async with app.run() as workflow_app:
            async with gen_client("temporal", server_registry=workflow_app.context.server_registry) as client:
                tool_params = {"run_id": run_id}
                if payload:
                    tool_params["payload"] = payload
                
                result = await client.call_tool("workflows-resume", tool_params)
                
                success = result.content[0].text if result.content else False
                if isinstance(success, str):
                    success = success.lower() == 'true'
                
                if success:
                    console.print(f"[green]✓[/green] Successfully resumed workflow")
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                else:
                    raise CLIError(f"Failed to resume workflow with run ID {run_id}")
                    
    except Exception as e:
        raise CLIError(f"Error resuming workflow with run ID {run_id}: {str(e)}") from e


def resume_workflow(
    run_id: str = typer.Argument(..., help="Run ID of the workflow to resume"),
    payload: Optional[str] = typer.Option(None, "--payload", help="JSON or text payload to pass to resumed workflow"),
) -> None:
    """Resume a suspended workflow execution.
    
    Resumes execution of a previously suspended workflow. Optionally accepts
    a payload (JSON or text) to pass data to the resumed workflow.
    
    Examples:
        mcp-agent cloud workflows resume run_abc123
        mcp-agent cloud workflows resume run_abc123 --payload '{"data": "value"}'
        mcp-agent cloud workflows resume run_abc123 --payload "simple text"
    """
    if payload:
        try:
            json.loads(payload)
            console.print(f"[dim]Resuming with JSON payload...[/dim]")
        except json.JSONDecodeError:
            console.print(f"[dim]Resuming with text payload...[/dim]")

    run_async(_resume_workflow_async(run_id, payload))