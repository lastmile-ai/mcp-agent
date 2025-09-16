import json
import sys
from typing import Optional

import typer
from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
)
from mcp_agent.cli.core.utils import run_async
from ...utils import resolve_server
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import AppServerInfo, MCPAppClient
from mcp_agent.cli.mcp_app.mcp_client import (
    MCPClientSession,
    mcp_connection_session,
)
from mcp_agent.cli.utils.ux import (
    console,
    print_error,
)


def get_app_status(
    app_id_or_url: str = typer.Option(
        None,
        "--id",
        "-i",
        help="ID, server URL, or name of the app to get details for.",
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
    """Get server details -- such as available tools, prompts, resources, and workflows -- for an MCP App."""
    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in to get app status. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option.",
            retriable=False,
        )

    client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    if not app_id_or_url:
        raise CLIError("You must provide an app ID or server URL to get its status.")

    try:
        app_or_config = resolve_server(client, app_id_or_url)

        if not app_or_config:
            raise CLIError(f"App or config with ID or URL '{app_id_or_url}' not found.")

        if not app_or_config.appServerInfo:
            raise CLIError(
                f"App or config with ID or URL '{app_id_or_url}' has no server info available."
            )

        print_server_info(app_or_config.appServerInfo)

        server_url = app_or_config.appServerInfo.serverUrl
        if server_url:
            run_async(
                print_mcp_server_details(
                    server_url=server_url, api_key=effective_api_key
                )
            )
        else:
            raise CLIError("No server URL available for this app.")

    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key.",
            retriable=False,
        ) from e
    except Exception as e:
        # Re-raise with more context - top-level CLI handler will show clean message
        raise CLIError(
            f"Error getting status for app or config with ID or URL {app_id_or_url}: {str(e)}"
        ) from e


def print_server_info(server_info: AppServerInfo) -> None:
    console.print(
        Panel(
            f"Server URL: [cyan]{server_info.serverUrl}[/cyan]\n"
            f"Server Status: [cyan]{_server_status_text(server_info.status)}[/cyan]",
            title="Server Info",
            border_style="blue",
            expand=False,
        )
    )


def _server_status_text(status: str) -> str:
    if status == "APP_SERVER_STATUS_ONLINE":
        return "🟢 Online"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return "🔴 Offline"
    else:
        return "❓ Unknown"


async def print_mcp_server_details(server_url: str, api_key: str) -> None:
    """Prints the MCP server details."""
    try:
        async with mcp_connection_session(server_url, api_key) as mcp_client_session:
            choices = {
                "1": "Show Server Tools",
                "2": "Show Server Prompts",
                "3": "Show Server Resources",
                "4": "Show Server Workflows",
                "0": "Show All",
            }

            # Print the numbered options
            console.print("\n[bold]What would you like to display?[/bold]")
            for key, description in choices.items():
                console.print(f"[cyan]{key}[/cyan]: {description}")

            if sys.stdout.isatty():
                try:
                    choice = Prompt.ask(
                        "\nWhat would you like to display?",
                        choices=list(choices.keys()),
                        default="0",
                        show_choices=False,
                    )
                except (EOFError, KeyboardInterrupt):
                    return
            else:
                console.print("Choosing 0 (Show All)")
                choice = "0"

            if choice in ["0", "1"]:
                await print_server_tools(mcp_client_session)
            if choice in ["0", "2"]:
                await print_server_prompts(mcp_client_session)
            if choice in ["0", "3"]:
                await print_server_resources(mcp_client_session)
            if choice in ["0", "4"]:
                await print_server_workflows(mcp_client_session)

    except Exception as e:
        raise CLIError(
            f"Error obtaining details from MCP server at {server_url}: {str(e)}"
        ) from e


async def print_server_tools(session: MCPClientSession) -> None:
    """Prints the available tools on the MCP server."""
    try:
        with console.status("[bold green]Fetching server tools...", spinner="dots"):
            res = await session.list_tools()

        if not res.tools:
            console.print(
                Panel(
                    "[yellow]No tools found[/yellow]",
                    title="Server Tools",
                    border_style="blue",
                )
            )
            return

        panels = []

        for tool in res.tools:
            # Tool name and description
            header = Text(f"{tool.name}", style="bold cyan")
            desc = tool.description or "No description available"
            body_parts: list = [Text(desc, style="white")]

            # Input schema
            if tool.inputSchema:
                schema_str = json.dumps(tool.inputSchema, indent=2)
                schema_syntax = Syntax(
                    schema_str, "json", theme="monokai", word_wrap=True
                )
                body_parts.append(Text("\nTool Parameters:", style="bold magenta"))
                body_parts.append(schema_syntax)

            body = Group(*body_parts)

            panels.append(
                Panel(
                    body,
                    title=header,
                    border_style="green",
                    expand=False,
                )
            )

        console.print(Panel(Group(*panels), title="Server Tools", border_style="blue"))

    except Exception as e:
        print_error(f"Error fetching tools: {str(e)}")


async def print_server_prompts(session: MCPClientSession) -> None:
    """Prints the available prompts on the MCP server."""
    try:
        with console.status("[bold green]Fetching server prompts...", spinner="dots"):
            res = await session.list_prompts()
        if not res.prompts or len(res.prompts) == 0:
            console.print(
                Panel(
                    "[yellow]No prompts found[/yellow]",
                    title="Server Prompts",
                    border_style="blue",
                )
            )
            return

        panels = []
        for prompt in res.prompts:
            header = Text(f"{prompt.name}", style="bold cyan")
            desc = prompt.description or "No description available"
            body_parts: list = [Text(desc, style="white")]
            if prompt.arguments:
                for arg in prompt.arguments:
                    # name, description, required
                    arg_required = "(required)" if arg.required else "(optional)"
                    arg_header = Text(
                        f"\nParameter: {arg.name} {arg_required}",
                        style="bold magenta",
                    )
                    arg_desc = arg.description or "No description available"
                    body_parts.append(arg_header)
                    body_parts.append(Text(arg_desc, style="white"))
            body = Group(*body_parts)
            panels.append(
                Panel(
                    body,
                    title=header,
                    border_style="green",
                    expand=False,
                )
            )
        console.print(
            Panel(Group(*panels), title="Server Prompts", border_style="blue")
        )
    except Exception as e:
        print_error(f"Error fetching prompts: {str(e)}")


async def print_server_resources(session: MCPClientSession) -> None:
    """Prints the available resources on the MCP server."""
    try:
        with console.status("[bold green]Fetching server resources...", spinner="dots"):
            res = await session.list_resources()

        if not res.resources or len(res.resources) == 0:
            console.print(
                Panel(
                    "[yellow]No resources found[/yellow]",
                    title="Server Resources",
                    border_style="blue",
                )
            )
            return

        table = Table(border_style="green", expand=True)
        table.add_column("URI", style="cyan", no_wrap=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="white", overflow="fold")
        table.add_column("MIME Type", style="yellow", overflow="fold")
        table.add_column("Size", style="green", overflow="fold")
        for resource in res.resources:
            table.add_row(
                resource.uri.encoded_string(),
                resource.name,
                resource.description or "N/A",
                resource.mimeType or "N/A",
                resource.size and str(resource.size) or "N/A",
            )
        console.print(Panel(table, title="Server Resources", border_style="blue"))
    except Exception as e:
        print_error(f"Error fetching resources: {str(e)}")


async def print_server_workflows(session: MCPClientSession) -> None:
    """Prints the available workflows on the MCP server."""
    try:
        with console.status("[bold green]Fetching server workflows...", spinner="dots"):
            res = await session.list_workflows()

        if not res.workflows or len(res.workflows) == 0:
            console.print(
                Panel(
                    "[yellow]No workflows found[/yellow]",
                    title="Server Workflows",
                    border_style="blue",
                )
            )
            return

        panels = []
        for workflow in res.workflows:
            header = Text(f"{workflow.name}", style="bold cyan")
            desc = workflow.description or "No description available"
            body_parts: list = [Text(desc, style="white")]
            body = Group(*body_parts)
            panels.append(
                Panel(
                    body,
                    title=header,
                    border_style="green",
                    expand=False,
                )
            )
        console.print(
            Panel(Group(*panels), title="Server Workflows", border_style="blue")
        )
    except Exception as e:
        print_error(f"Error fetching workflows: {str(e)}")
