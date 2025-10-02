"""Workflow describe command implementation."""

import json
from datetime import datetime
from typing import Optional

import typer
import yaml

from mcp_agent.cli.auth.main import load_api_key_credentials
from mcp_agent.cli.cloud.commands.workflows.utils import format_workflow_status
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mcp_client import WorkflowRun, mcp_connection_session
from mcp_agent.cli.utils.ux import console, print_error

from ...utils import (
    handle_server_api_errors,
    resolve_server_async,
    setup_authenticated_client,
)


async def _describe_workflow_async(
    server_id_or_url_or_name: str, run_id: str, format: str = "text"
) -> None:
    """Describe a workflow using MCP tool calls to a deployed server."""
    if server_id_or_url_or_name.startswith(("http://", "https://")):
        server_url = server_id_or_url_or_name
    else:
        client = setup_authenticated_client()
        server = await resolve_server_async(client, server_id_or_url_or_name)

        if hasattr(server, "appServerInfo") and server.appServerInfo:
            server_url = server.appServerInfo.serverUrl
        else:
            raise CLIError(
                f"Server '{server_id_or_url_or_name}' is not deployed or has no server URL"
            )

        if not server_url:
            raise CLIError(
                f"No server URL found for server '{server_id_or_url_or_name}'"
            )

    from mcp_agent.cli.config import settings as _settings

    effective_api_key = _settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in to access server. Run 'mcp-agent login'.",
            retriable=False,
        )

    try:
        async with mcp_connection_session(
            server_url, effective_api_key
        ) as mcp_client_session:
            try:
                workflow_status = await mcp_client_session.get_workflow_status(
                    run_id=run_id
                )
                print_workflow_status(workflow_status, format)
            except Exception as e:
                print_error(
                    f"Error getting workflow status from MCP server at {server_url}: {str(e)}"
                )

    except Exception as e:
        raise CLIError(
            f"Error describing workflow with run ID {run_id}: {str(e)}"
        ) from e


@handle_server_api_errors
def describe_workflow(
    server_id_or_url_or_name: str = typer.Argument(
        ..., help="App ID, server URL, or app name hosting the workflow"
    ),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to describe"),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """Describe a workflow execution (alias: status).

    Shows detailed information about a workflow execution including its current status,
    creation time, and other metadata.

    Examples:

        mcp-agent cloud workflows describe app_abc123 run_xyz789

        mcp-agent cloud workflows describe app_abc123 run_xyz789 --format json
    """
    if format not in ["text", "json", "yaml"]:
        console.print("[red]Error: --format must be 'text', 'json', or 'yaml'[/red]")
        raise typer.Exit(6)

    run_async(_describe_workflow_async(server_id_or_url_or_name, run_id, format))


def print_workflow_status(workflow_status: WorkflowRun, format: str = "text") -> None:
    """Print workflow status information in requested format"""

    if format == "json":
        print(json.dumps(workflow_status.model_dump(), indent=2))
    elif format == "yaml":
        print(yaml.dump(workflow_status.model_dump(), default_flow_style=False))
    else:  # text format
        name = getattr(workflow_status, "name", "Unknown")
        workflow_id = (
            getattr(workflow_status.temporal, "workflow_id", "Unknown")
            if workflow_status.temporal
            else "Unknown"
        )
        run_id = getattr(workflow_status, "id", "Unknown")
        status = getattr(workflow_status, "status", "Unknown")

        # Try to get creation time from temporal metadata
        created_at = (
            getattr(workflow_status.temporal, "start_time", None)
            if workflow_status.temporal
            else None
        )
        if created_at is not None:
            try:
                created_dt = datetime.fromtimestamp(created_at)
                created_at = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                created_at = str(created_at)
        else:
            created_at = "Unknown"

        console.print("\n[bold blue]🔍 Workflow Details[/bold blue]")
        console.print()
        console.print(f"[bold cyan]{name}[/bold cyan] {format_workflow_status(status)}")
        console.print(f"  Workflow ID: {workflow_id}")
        console.print(f"  Run ID: {run_id}")
        console.print(f"  Created: {created_at}")

        # Print result information if available
        if workflow_status.result:
            console.print("\n[bold green]📄 Result[/bold green]")
            console.print(
                f"  Kind: {getattr(workflow_status.result, 'kind', 'Unknown')}"
            )

            result_value = getattr(workflow_status.result, "value", None)
            if result_value:
                # Truncate very long results
                if len(str(result_value)) > 10000:
                    truncated_value = str(result_value)[:10000] + "..."
                    console.print(f"  Value: {truncated_value}")
                else:
                    console.print(f"  Value: {result_value}")

            # Print timing if available
            start_time = getattr(workflow_status.result, "start_time", None)
            end_time = getattr(workflow_status.result, "end_time", None)
            if start_time:
                start_dt = datetime.fromtimestamp(start_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                console.print(f"  Started: {start_dt}")
            if end_time:
                end_dt = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")
                console.print(f"  Ended: {end_dt}")

        # Print error information if available
        if workflow_status.error:
            console.print("\n[bold red]❌ Error[/bold red]")
            console.print(f"  {workflow_status.error}")

        # Print state error if different from main error
        if (
            workflow_status.state
            and workflow_status.state.error
            and workflow_status.state.error != workflow_status.error
        ):
            console.print("\n[bold red]⚠️  State Error[/bold red]")
            if isinstance(workflow_status.state.error, dict):
                error_type = workflow_status.state.error.get("type", "Unknown")
                error_message = workflow_status.state.error.get(
                    "message", "Unknown error"
                )
                console.print(f"  Type: {error_type}")
                console.print(f"  Message: {error_message}")
            else:
                console.print(f"  {workflow_status.state.error}")
