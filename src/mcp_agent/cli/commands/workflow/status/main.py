from typing import Optional

import typer
from mcp_agent_cloud.auth import load_api_key_credentials
from mcp_agent_cloud.config import settings
from mcp_agent_cloud.core.api_client import UnauthenticatedError
from mcp_agent_cloud.core.constants import ENV_API_BASE_URL, ENV_API_KEY
from mcp_agent_cloud.core.utils import run_async
from mcp_agent_cloud.ux import console, print_error
from mcp_agent_cloud.workflows.api_client import (
    WorkflowAPIClient,
    WorkflowInfo,
)
from rich.panel import Panel


def get_workflow_status(
    workflow_id: str = typer.Option(
        None,
        "--id",
        "-i",
        help="ID of the workflow to get details for.",
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
        envvar=ENV_API_BASE_URL,
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
        envvar=ENV_API_KEY,
    ),
) -> None:
    """Get workflow status."""
    effective_api_key = (
        api_key or settings.API_KEY or load_api_key_credentials()
    )

    if not effective_api_key:
        print_error(
            "Must be logged in to get workflow status. Run 'mcp-agent login --force', set MCP_API_KEY environment variable or specify --api-key option."
        )
        raise typer.Exit(1)

    client = WorkflowAPIClient(api_url=api_url, api_key=effective_api_key)

    if not workflow_id:
        print_error("You must provide a workflow ID to get its status.")
        raise typer.Exit(1)

    try:
        workflow_info = run_async(client.get_workflow(workflow_id))

        if not workflow_info:
            print_error(f"Workflow with ID '{workflow_id}' not found.")
            raise typer.Exit(1)

        print_workflow_info(workflow_info)

    except UnauthenticatedError as e:
        print_error(
            "Invalid API key. Run 'mcp-agent login --force' or set MCP_API_KEY environment variable with new API key."
        )
        raise typer.Exit(1) from e
    except Exception as e:
        print_error(
            f"Error getting status for workflow with ID {workflow_id}: {str(e)}"
        )
        raise typer.Exit(1)


def print_workflow_info(workflow_info: WorkflowInfo) -> None:
    console.print(
        Panel(
            f"Name: [cyan]{workflow_info.name}[/cyan]\n"
            f"ID: [cyan]{workflow_info.workflowId}[/cyan]\n"
            f"Run ID: [cyan]{workflow_info.runId or 'N/A'}[/cyan]\n"
            f"Created: [cyan]{workflow_info.createdAt.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]\n"
            f"Status: [cyan]{_execution_status_text(workflow_info.executionStatus)}[/cyan]",
            title="Workflow",
            border_style="blue",
            expand=False,
        )
    )


def _execution_status_text(status: Optional[str]) -> str:
    """Format the execution status text."""
    match status:
        case "WORKFLOW_EXECUTION_STATUS_RUNNING":
            return "🔄 Running"
        case "WORKFLOW_EXECUTION_STATUS_FAILED":
            return "❌ Failed"
        case "WORKFLOW_EXECUTION_STATUS_TIMED_OUT":
            return "⌛ Timed Out"
        case "WORKFLOW_EXECUTION_STATUS_CANCELLED":
            return "🚫 Cancelled"
        case "WORKFLOW_EXECUTION_STATUS_TERMINATED":
            return "🛑 Terminated"
        case "WORKFLOW_EXECUTION_STATUS_COMPLETED":
            return "✅ Completed"
        case "WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW":
            return "🔁 Continued as New"
        case _:
            return "❓ Unknown"
