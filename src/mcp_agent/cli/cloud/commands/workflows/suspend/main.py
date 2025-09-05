"""Workflow suspend command implementation."""

import typer

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.cli.workflows.api_client import WorkflowAPIClient


def suspend_workflow(
    run_id: str = typer.Argument(..., help="Run ID of the workflow to suspend"),
) -> None:
    """Suspend a workflow execution.
    
    Pauses the execution of a running workflow. The workflow can be resumed later
    using the resume command.
    """
    effective_api_key = load_api_key_credentials()
    if not effective_api_key:
        raise CLIError(
            "Must be logged in to suspend workflow. Run 'mcp-agent login' or set MCP_API_KEY environment variable."
        )

    client = WorkflowAPIClient(api_url=DEFAULT_API_BASE_URL, api_key=effective_api_key)

    try:
        # Note: Using run_id as workflow_id since the spec uses run-id as the argument
        # but the backend API expects workflow_id. This may need adjustment based on
        # how the backend interprets the workflow identification.
        workflow_info = run_async(client.suspend_workflow(workflow_id=run_id))

        console.print(f"[green]✓[/green] Successfully suspended workflow")
        console.print(f"  Workflow ID: [cyan]{workflow_info.workflowId}[/cyan]")
        console.print(f"  Run ID: [cyan]{workflow_info.runId or 'N/A'}[/cyan]")
        console.print(f"  Status: [cyan]{_execution_status_text(workflow_info.executionStatus)}[/cyan]")

    except UnauthenticatedError as e:
        raise CLIError(
            "Authentication failed. Try running 'mcp-agent login'"
        ) from e
    except Exception as e:
        raise CLIError(f"Error suspending workflow with run ID {run_id}: {str(e)}") from e


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