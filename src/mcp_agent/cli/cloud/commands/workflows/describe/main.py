"""Workflow describe command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.panel import Panel

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console
from mcp_agent.cli.workflows.api_client import WorkflowAPIClient, WorkflowInfo


def describe_workflow(
    run_id: str = typer.Argument(..., help="Run ID of the workflow to describe"),
    format: Optional[str] = typer.Option("text", "--format", help="Output format (text|json|yaml)"),
) -> None:
    """Describe a workflow execution (alias: status).
    
    Shows detailed information about a workflow execution including its current status,
    creation time, and other metadata.
    """
    # Validate format
    if format not in ["text", "json", "yaml"]:
        console.print("[red]Error: --format must be 'text', 'json', or 'yaml'[/red]")
        raise typer.Exit(6)

    effective_api_key = load_api_key_credentials()
    if not effective_api_key:
        raise CLIError(
            "Must be logged in to describe workflow. Run 'mcp-agent login' or set MCP_API_KEY environment variable."
        )

    client = WorkflowAPIClient(api_url=DEFAULT_API_BASE_URL, api_key=effective_api_key)

    try:
        workflow_info = run_async(client.get_workflow(run_id))

        if not workflow_info:
            raise CLIError(f"Workflow with run ID '{run_id}' not found.")

        if format == "json":
            print(json.dumps(_workflow_to_dict(workflow_info), indent=2))
        elif format == "yaml":
            print(yaml.dump(_workflow_to_dict(workflow_info), default_flow_style=False))
        else:  # text format
            print_workflow_info(workflow_info)

    except UnauthenticatedError as e:
        raise CLIError(
            "Authentication failed. Try running 'mcp-agent login'"
        ) from e
    except Exception as e:
        raise CLIError(f"Error describing workflow with run ID {run_id}: {str(e)}") from e


def print_workflow_info(workflow_info: WorkflowInfo) -> None:
    """Print workflow information in text format."""
    console.print(
        Panel(
            f"Name: [cyan]{workflow_info.name}[/cyan]\n"
            f"Workflow ID: [cyan]{workflow_info.workflowId}[/cyan]\n"
            f"Run ID: [cyan]{workflow_info.runId or 'N/A'}[/cyan]\n"
            f"Created: [cyan]{workflow_info.createdAt.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]\n"
            f"Creator: [cyan]{workflow_info.principalId}[/cyan]\n"
            f"Status: [cyan]{_execution_status_text(workflow_info.executionStatus)}[/cyan]",
            title="Workflow",
            border_style="blue",
            expand=False,
        )
    )


def _workflow_to_dict(workflow_info: WorkflowInfo) -> dict:
    """Convert workflow info to dictionary for JSON/YAML output."""
    return {
        "name": workflow_info.name,
        "workflowId": workflow_info.workflowId,
        "runId": workflow_info.runId,
        "createdAt": workflow_info.createdAt.isoformat(),
        "creator": workflow_info.principalId,
        "executionStatus": workflow_info.executionStatus,
        "status": _execution_status_text(workflow_info.executionStatus),
    }


def _execution_status_text(status: Optional[str]) -> str:
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