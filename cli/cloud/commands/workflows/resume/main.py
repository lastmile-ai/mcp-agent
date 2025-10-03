"""Workflow resume command implementation."""

import json
from typing import Any, Dict, Optional

import typer

from mcp_agent.cli.auth.main import load_api_key_credentials
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mcp_client import mcp_connection_session
from mcp_agent.cli.utils.ux import console, print_error
from ...utils import (
    setup_authenticated_client,
    handle_server_api_errors,
    resolve_server_async,
)


async def _signal_workflow_async(
    server_id_or_url_or_name: str,
    run_id: str,
    signal_name: str = "resume",
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Send a signal to a workflow using MCP tool calls to a deployed server."""
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
                action_present = (
                    "Resuming"
                    if signal_name == "resume"
                    else "Suspending"
                    if signal_name == "suspend"
                    else f"Signaling ({signal_name})"
                )

                with console.status(
                    f"[bold blue]{action_present} workflow...", spinner="dots"
                ):
                    success = await mcp_client_session.resume_workflow(
                        run_id, signal_name, payload
                    )

                if success:
                    action_past = (
                        "resumed"
                        if signal_name == "resume"
                        else "suspended"
                        if signal_name == "suspend"
                        else f"signaled ({signal_name})"
                    )
                    action_color = (
                        "green"
                        if signal_name == "resume"
                        else "yellow"
                        if signal_name == "suspend"
                        else "blue"
                    )
                    action_icon = (
                        "✓"
                        if signal_name == "resume"
                        else "⏸"
                        if signal_name == "suspend"
                        else "📡"
                    )
                    console.print()
                    console.print(
                        f"[{action_color}]{action_icon} Successfully {action_past} workflow[/{action_color}]"
                    )
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                else:
                    print_error(
                        f"Failed to {signal_name} workflow with run ID {run_id}"
                    )
            except Exception as e:
                # Don't raise or it will be a generic unhandled error in TaskGroup
                print_error(
                    f"Error {signal_name}ing workflow with run ID {run_id}: {str(e)}"
                )

    except Exception as e:
        raise CLIError(
            f"Error {signal_name}ing workflow with run ID {run_id}: {str(e)}"
        ) from e


@handle_server_api_errors
def resume_workflow(
    server_id_or_url_or_name: str = typer.Argument(
        ..., help="App ID, server URL, or app name hosting the workflow"
    ),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to resume"),
    signal_name: Optional[str] = "resume",
    payload: Optional[str] = typer.Option(
        None,
        "--payload",
        help="JSON payload to pass to resumed workflow",
    ),
) -> None:
    """Resume a suspended workflow execution.

    Resumes execution of a previously suspended workflow. Optionally accepts a signal
    name and a payload (JSON) to pass data to the resumed workflow.

    Examples:

        mcp-agent cloud workflows resume app_abc123 run_xyz789

        mcp-agent cloud workflows resume app_abc123 run_xyz789 --payload '{"data": "value"}'

        mcp-agent cloud workflows resume app_abc123 run_xyz789 --signal-name provide_human_input --payload '{"response": "Your input here"}'
    """
    if payload:
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON payload: {str(e)}") from e

    run_async(
        _signal_workflow_async(
            server_id_or_url_or_name, run_id, signal_name or "resume", payload
        )
    )


@handle_server_api_errors
def suspend_workflow(
    server_id_or_url_or_name: str = typer.Argument(
        ..., help="App ID, server URL, or app name hosting the workflow"
    ),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to suspend"),
    payload: Optional[str] = typer.Option(
        None, "--payload", help="JSON payload to pass to suspended workflow"
    ),
) -> None:
    """Suspend a workflow execution.

    Temporarily pauses a workflow execution, which can later be resumed.
    Optionally accepts a payload (JSON) to pass data to the suspended workflow.

    Examples:
        mcp-agent cloud workflows suspend app_abc123 run_xyz789
        mcp-agent cloud workflows suspend https://server.example.com run_xyz789 --payload '{"reason": "maintenance"}'
    """
    if payload:
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON payload: {str(e)}") from e

    run_async(
        _signal_workflow_async(server_id_or_url_or_name, run_id, "suspend", payload)
    )
