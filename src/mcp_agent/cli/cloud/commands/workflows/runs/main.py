"""Workflow runs command implementation."""

import json
from typing import Optional

import typer
import yaml

from mcp_agent.cli.auth.main import load_api_key_credentials
from mcp_agent.cli.cloud.commands.workflows.utils import (
    print_workflow_runs,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mcp_client import WorkflowRun, mcp_connection_session
from mcp_agent.cli.utils.ux import console, print_error

from ...utils import (
    resolve_server_async,
    setup_authenticated_client,
    validate_output_format,
)


async def _list_workflow_runs_async(
    server_id_or_url: str, limit: Optional[int], status: Optional[str], format: str
) -> None:
    """List workflow runs using MCP tool calls to a deployed server."""
    if server_id_or_url.startswith(("http://", "https://")):
        server_url = server_id_or_url
    else:
        client = setup_authenticated_client()
        server = await resolve_server_async(client, server_id_or_url)

        if hasattr(server, "appServerInfo") and server.appServerInfo:
            server_url = server.appServerInfo.serverUrl
        else:
            raise CLIError(
                f"Server '{server_id_or_url}' is not deployed or has no server URL"
            )

        if not server_url:
            raise CLIError(f"No server URL found for server '{server_id_or_url}'")

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
                with console.status(
                    "[bold green]Fetching workflow runs...", spinner="dots"
                ):
                    result = await mcp_client_session.list_workflow_runs()

                workflows = (
                    result.workflow_runs if result and result.workflow_runs else []
                )

                if status:
                    workflows = [w for w in workflows if _matches_status(w, status)]

                if limit:
                    workflows = workflows[:limit]

                if format == "json":
                    _print_workflows_json(workflows)
                elif format == "yaml":
                    _print_workflows_yaml(workflows)
                else:
                    print_workflow_runs(workflows, status)
            except Exception as e:
                print_error(
                    f"Error listing workflow runs for server {server_id_or_url}: {str(e)}"
                )

    except Exception as e:
        raise CLIError(
            f"Error listing workflow runs for server {server_id_or_url}: {str(e)}"
        ) from e


def list_workflow_runs(
    server_id_or_url: str = typer.Argument(
        ..., help="App ID, server URL, or app name to list workflow runs for"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Maximum number of results to return"
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filter by status: running|failed|timed_out|timeout|canceled|terminated|completed|continued",
        callback=lambda value: _get_status_filter(value) if value else None,
    ),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """List workflow runs for an MCP Server.

    Examples:

        mcp-agent cloud workflows runs app_abc123

        mcp-agent cloud workflows runs https://server.example.com --status running

        mcp-agent cloud workflows runs apcnf_xyz789 --limit 10 --format json
    """
    validate_output_format(format)
    run_async(_list_workflow_runs_async(server_id_or_url, limit, status, format))


def _get_status_filter(status: str) -> str:
    """Convert status string to normalized status."""
    status_map = {
        "running": "running",
        "failed": "error",
        "error": "error",
        "timed_out": "timed_out",
        "timeout": "timed_out",  # alias
        "canceled": "canceled",
        "cancelled": "canceled",  # alias
        "terminated": "terminated",
        "completed": "completed",
        "continued": "continued",
        "continued_as_new": "continued",
    }
    normalized_status = status_map.get(status.lower())
    if not normalized_status:
        valid_statuses = (
            "running|failed|timed_out|timeout|canceled|terminated|completed|continued"
        )
        raise typer.BadParameter(
            f"Invalid status '{status}'. Valid options: {valid_statuses}"
        )
    return normalized_status


def _matches_status(workflow, status_filter: str) -> bool:
    """Check if workflow matches the status filter.

    Note: We use string-based matching instead of protobuf enum values because
    the MCP tool response format returns status as strings, not enum objects.
    This approach is more flexible and doesn't require maintaining sync with
    the protobuf definitions.
    """
    if isinstance(workflow, dict):
        workflow_status = workflow.get("status", "")
    else:
        workflow_status = getattr(workflow, "status", "")

    if isinstance(workflow_status, str):
        return status_filter.lower() in workflow_status.lower()
    return False


def _print_workflows_json(workflows: list[WorkflowRun]):
    """Print workflows in JSON format."""
    workflows_data = [workflow.model_dump() for workflow in workflows]
    print(json.dumps({"workflow_runs": workflows_data}, indent=2, default=str))


def _print_workflows_yaml(workflows: list[WorkflowRun]):
    """Print workflows in YAML format."""
    workflows_data = [workflow.model_dump() for workflow in workflows]
    print(yaml.dump({"workflow_runs": workflows_data}, default_flow_style=False))
