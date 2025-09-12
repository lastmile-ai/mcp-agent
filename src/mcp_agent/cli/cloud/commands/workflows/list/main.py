"""Workflow list command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.table import Table

from mcp_agent.cli.auth.main import load_api_key_credentials
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mcp_client import mcp_connection_session
from mcp_agent.cli.utils.ux import console, print_info, print_error
from ...utils import (
    setup_authenticated_client,
    resolve_server,
    handle_server_api_errors,
    validate_output_format,
)


async def _list_workflows_async(server_id_or_url: str, format: str = "text") -> None:
    """List available workflows using MCP tool calls to a deployed server."""
    if server_id_or_url.startswith(("http://", "https://")):
        server_url = server_id_or_url
    else:
        client = setup_authenticated_client()
        server = resolve_server(client, server_id_or_url)

        if hasattr(server, "appServerInfo") and server.appServerInfo:
            server_url = server.appServerInfo.serverUrl
        else:
            raise CLIError(
                f"Server '{server_id_or_url}' is not deployed or has no server URL"
            )

        if not server_url:
            raise CLIError(f"No server URL found for server '{server_id_or_url}'")

    effective_api_key = load_api_key_credentials()

    if not effective_api_key:
        raise CLIError("Must be logged in to access server. Run 'mcp-agent login'.")

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
                    print_workflows_text(workflows, server_id_or_url)
            except Exception as e:
                print_error(
                    f"Error listing workflows for server {server_id_or_url}: {str(e)}"
                )

    except Exception as e:
        raise CLIError(
            f"Error listing workflows for server {server_id_or_url}: {str(e)}"
        ) from e


@handle_server_api_errors
def list_workflows(
    server_id_or_url: str = typer.Argument(
        ..., help="Server ID or URL to list workflows for"
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
    run_async(_list_workflows_async(server_id_or_url, format))


def print_workflows_text(workflows, server_id_or_url: str) -> None:
    """Print workflows information in text format."""
    server_name = server_id_or_url

    console.print(
        f"\n[bold blue]📋 Available Workflows for Server: {server_name}[/bold blue]"
    )

    if not workflows:
        print_info("No workflows found for this server.")
        return

    console.print(f"\nFound {len(workflows)} workflow definition(s):")

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Description", style="green", width=40)
    table.add_column("Capabilities", style="yellow", width=25)
    table.add_column("Tool Endpoints", style="dim", width=20)

    for workflow in workflows:
        name = getattr(workflow, "name", "Unknown")
        description = getattr(workflow, "description", None) or "Unknown"
        capabilities = getattr(workflow, "capabilities", [])
        tool_endpoints = getattr(workflow, "tool_endpoints", [])

        capabilities_str = ", ".join(capabilities) if capabilities else "Unknown"
        tool_endpoints_str = (
            ", ".join([ep.split("-")[-1] for ep in tool_endpoints])
            if tool_endpoints
            else "Unknown"
        )

        table.add_row(
            _truncate_string(name, 25),
            _truncate_string(description, 40),
            _truncate_string(capabilities_str, 25),
            _truncate_string(tool_endpoints_str, 20),
        )

    console.print(table)


def _truncate_string(text: str, max_length: int) -> str:
    """Truncate string to max_length, adding ellipsis if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
