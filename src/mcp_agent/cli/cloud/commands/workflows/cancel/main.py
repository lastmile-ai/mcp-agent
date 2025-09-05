"""Workflow cancel command implementation."""

from typing import Optional

import typer

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.cli.workflows.api_client import WorkflowAPIClient


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
    effective_api_key = load_api_key_credentials()
    if not effective_api_key:
        raise CLIError(
            "Must be logged in to cancel workflow. Run 'mcp-agent login' or set MCP_API_KEY environment variable."
        )

    client = WorkflowAPIClient(api_url=DEFAULT_API_BASE_URL, api_key=effective_api_key)

    try:
        workflow_info = run_async(client.cancel_workflow(workflow_id=run_id, reason=reason))

        console.print(f"[yellow]⚠[/yellow] Successfully cancelled workflow")
        console.print(f"  Workflow ID: [cyan]{workflow_info.workflowId}[/cyan]")
        console.print(f"  Run ID: [cyan]{workflow_info.runId or 'N/A'}[/cyan]")
        console.print(f"  Status: [cyan]{_execution_status_text(workflow_info.executionStatus)}[/cyan]")
        
        if reason:
            console.print(f"  Reason: [dim]{reason}[/dim]")

    except UnauthenticatedError as e:
        raise CLIError(
            "Authentication failed. Try running 'mcp-agent login'"
        ) from e
    except Exception as e:
        raise CLIError(f"Error cancelling workflow with run ID {run_id}: {str(e)}") from e


def _execution_status_text(status: str | None) -> str:
    """Format the execution status text."""
    match status:
        case "WORKFLOW_EXECUTION_STATUS_RUNNING":
            return "🔄 Running"
        case "WORKFLOW_EXECUTION_STATUS_FAILED":
            return "❌ Failed"
        case "WORKFLOW_EXECUTION_STATUS_TIMED_OUT":
            return "⌛ Timed Out"
        case "WORKFLOW_EXECUTION_STATUS_CANCELED":
            return "🚫 Cancelled"
        case "WORKFLOW_EXECUTION_STATUS_TERMINATED":
            return "🛑 Terminated"
        case "WORKFLOW_EXECUTION_STATUS_COMPLETED":
            return "✅ Completed"
        case "WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW":
            return "🔁 Continued as New"
        case _:
            return "❓ Unknown"