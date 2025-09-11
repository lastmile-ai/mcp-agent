"""Workflow list command implementation."""

import json
from typing import Optional

import typer
import yaml
from rich.table import Table

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import console, print_info
from mcp_agent.config import MCPServerSettings, Settings, LoggerSettings
from mcp_agent.mcp.gen_client import gen_client
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

    quiet_settings = Settings(logger=LoggerSettings(level="error"))
    app = MCPApp(name="workflows_cli", settings=quiet_settings)

    try:
        async with app.run() as workflow_app:
            context = workflow_app.context

            sse_url = (
                f"{server_url}/sse" if not server_url.endswith("/sse") else server_url
            )
            context.server_registry.registry["workflow_server"] = MCPServerSettings(
                name="workflow_server",
                description=f"Deployed MCP server {server_url}",
                url=sse_url,
                transport="sse",
            )

            async with gen_client(
                "workflow_server", server_registry=context.server_registry
            ) as client:
                result = await client.call_tool("workflows-list", {})

                workflows_data = result.content[0].text if result.content else "{}"
                if isinstance(workflows_data, str):
                    workflows_data = json.loads(workflows_data)

                if not workflows_data:
                    workflows_data = {}

                if format == "json":
                    print(json.dumps(workflows_data, indent=2))
                elif format == "yaml":
                    print(yaml.dump(workflows_data, default_flow_style=False))
                else:  # text format
                    print_workflows_text(workflows_data, server_id_or_url)

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


def print_workflows_text(workflows_data: dict, server_id_or_url: str) -> None:
    """Print workflows information in text format."""
    server_name = server_id_or_url

    console.print(
        f"\n[bold blue]📋 Available Workflows for Server: {server_name}[/bold blue]"
    )

    if not workflows_data or not any(workflows_data.values()):
        print_info("No workflows found for this server.")
        return

    total_workflows = sum(
        len(workflow_list) if isinstance(workflow_list, list) else 1
        for workflow_list in workflows_data.values()
    )
    console.print(f"\nFound {total_workflows} workflow definition(s):")

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Description", style="green", width=40)
    table.add_column("Capabilities", style="yellow", width=25)
    table.add_column("Tool Endpoints", style="dim", width=20)

    for workflow_name, workflow_info in workflows_data.items():
        if isinstance(workflow_info, dict):
            name = workflow_info.get("name", workflow_name)
            description = workflow_info.get("description", "N/A")
            capabilities = ", ".join(workflow_info.get("capabilities", []))
            tool_endpoints = ", ".join(
                [ep.split("-")[-1] for ep in workflow_info.get("tool_endpoints", [])]
            )

            table.add_row(
                _truncate_string(name, 25),
                _truncate_string(description, 40),
                _truncate_string(capabilities if capabilities else "N/A", 25),
                _truncate_string(tool_endpoints if tool_endpoints else "N/A", 20),
            )

    console.print(table)


def _truncate_string(text: str, max_length: int) -> str:
    """Truncate string to max_length, adding ellipsis if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
