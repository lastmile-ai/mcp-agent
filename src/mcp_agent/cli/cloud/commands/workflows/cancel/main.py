"""Workflow cancel command implementation."""

from typing import Optional

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


async def _cancel_workflow_async(
    server_id_or_url_or_name: str, run_id: str, reason: Optional[str] = None
) -> None:
    """Cancel a workflow using MCP tool calls to a deployed server."""
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
                with console.status(
                    "[bold yellow]Cancelling workflow...", spinner="dots"
                ):
                    success = await mcp_client_session.cancel_workflow(run_id)

                if success:
                    console.print()
                    console.print("[yellow]🚫 Successfully cancelled workflow[/yellow]")
                    console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
                    if reason:
                        console.print(f"  Reason: [dim]{reason}[/dim]")
                else:
                    print_error(f"Failed to cancel workflow with run ID {run_id}")
            except Exception as e:
                print_error(f"Error cancelling workflow with run ID {run_id}: {str(e)}")

    except Exception as e:
        raise CLIError(
            f"Error cancelling workflow with run ID {run_id}: {str(e)}"
        ) from e


@handle_server_api_errors
def cancel_workflow(
    server_id_or_url_or_name: str = typer.Argument(
        ..., help="App ID, server URL, or app name hosting the workflow"
    ),
    run_id: str = typer.Argument(..., help="Run ID of the workflow to cancel"),
    reason: Optional[str] = typer.Option(
        None, "--reason", help="Optional reason for cancellation"
    ),
) -> None:
    """Cancel a workflow execution.

    Permanently stops a workflow execution. Unlike suspend, a cancelled workflow
    cannot be resumed and will be marked as cancelled.

    Examples:

        mcp-agent cloud workflows cancel app_abc123 run_xyz789

        mcp-agent cloud workflows cancel app_abc123 run_xyz789 --reason "User requested"
    """
    run_async(_cancel_workflow_async(server_id_or_url_or_name, run_id, reason))
