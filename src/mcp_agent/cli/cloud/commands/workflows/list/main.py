"""Workflow list command implementation."""

import json
from typing import Optional

import typer
import yaml

from mcp_agent.cli.auth.main import load_api_key_credentials
from mcp_agent.cli.cloud.commands.workflows.utils import print_workflows
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mcp_client import mcp_connection_session
from mcp_agent.cli.utils.ux import console, print_error
from ...utils import (
    setup_authenticated_client,
    resolve_server_async,
    handle_server_api_errors,
    validate_output_format,
)


async def _list_workflows_async(
    server_id_or_url_or_name: str, format: str = "text"
) -> None:
    """List available workflows using MCP tool calls to a deployed server."""
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
                    "[bold green]Fetching workflows...", spinner="dots"
                ):
                    result = await mcp_client_session.list_workflows()

                workflows = result.workflows if result and result.workflows else []

                if format == "json":
                    workflows_data = [workflow.model_dump() for workflow in workflows]
                    print(
                        json.dumps({"workflows": workflows_data}, indent=2, default=str)
                    )
                elif format == "yaml":
                    workflows_data = [workflow.model_dump() for workflow in workflows]
                    print(
                        yaml.dump(
                            {"workflows": workflows_data}, default_flow_style=False
                        )
                    )
                else:  # text format
                    print_workflows(workflows)
            except Exception as e:
                print_error(
                    f"Error listing workflows for server {server_id_or_url_or_name}: {str(e)}"
                )

    except Exception as e:
        raise CLIError(
            f"Error listing workflows for server {server_id_or_url_or_name}: {str(e)}"
        ) from e


@handle_server_api_errors
def list_workflows(
    server_id_or_url_or_name: str = typer.Argument(
        ..., help="App ID, server URL, or app name to list workflows for"
    ),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """List available workflow definitions for an MCP Server.

    This command lists the workflow definitions that a server provides,
    showing what workflows can be executed.

    Examples:

        mcp-agent cloud workflows list app_abc123

        mcp-agent cloud workflows list https://server.example.com --format json
    """
    validate_output_format(format)
    run_async(_list_workflows_async(server_id_or_url_or_name, format))
