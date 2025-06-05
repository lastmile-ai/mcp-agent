from typing import List, Optional

import typer
from mcp_agent_cloud.auth import load_api_key_credentials
from mcp_agent_cloud.config import settings
from mcp_agent_cloud.core.api_client import UnauthenticatedError
from mcp_agent_cloud.core.constants import ENV_API_BASE_URL, ENV_API_KEY
from mcp_agent_cloud.core.utils import run_async
from mcp_agent_cloud.mcp_app.api_client import MCPApp, MCPAppClient
from mcp_agent_cloud.ux import console, print_error, print_info
from rich.panel import Panel
from rich.table import Table


def list_apps(
    name_filter: str = typer.Option(
        None, "--name", "-n", help="Filter apps by name"
    ),
    max_results: int = typer.Option(
        100, "--max-results", "-m", help="Maximum number of results to return"
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
    """List MCP Apps with optional filtering by name."""
    effective_api_key = (
        api_key or settings.API_KEY or load_api_key_credentials()
    )
    client = MCPAppClient(api_url=api_url, api_key=effective_api_key)

    try:
        list_apps_res = run_async(
            client.list_apps(name_filter=name_filter, max_results=max_results)
        )

        print_info_header()

        if list_apps_res.apps:
            num_apps = list_apps_res.totalCount or len(list_apps_res.apps)
            print_info(f"Found {num_apps} deployed app(s):")
            print_apps(list_apps_res.apps)
        else:
            print_info("No deployed apps found.")

        print_info(
            "No configured apps found."
        )  # TODO: Implement configured apps listing

    except UnauthenticatedError as e:
        print_error(
            "Invalid API key. Run 'mcp-agent login --force' or set MCP_API_KEY environment variable with new API key."
        )
        raise typer.Exit(1) from e
    except Exception as e:
        print_error(f"Error checking or creating app: {str(e)}")
        raise typer.Exit(1)


def print_info_header() -> None:
    """Print a styled header explaining the following tables"""
    console.print(
        Panel(
            "Deployed Apps: [cyan]MCP Apps which you have bundled and deployed, as a developer[/cyan]\n"
            "Configured Apps: [cyan]MCP Apps which you have configured to use with your MCP clients[/cyan]",
            title="MCP Apps",
            border_style="blue",
            expand=False,
        )
    )


def print_apps(apps: List[MCPApp]) -> None:
    """Print a summary table of the app information."""
    table = Table(title="Deployed MCP Apps", expand=False, border_style="blue")

    table.add_column("Name", style="cyan")
    table.add_column("ID", style="bright_blue")
    table.add_column("Description", style="cyan")
    table.add_column("Server URL", style="bright_blue", no_wrap=True)
    table.add_column("Status", style="bright_blue", no_wrap=True)
    table.add_column("Created", style="cyan")

    for app in apps:
        server_url = ""
        server_status = "Unknown"

        if app.appServerInfo:
            server_url = app.appServerInfo.serverUrl
            server_status = (
                "🟢 Online" if app.appServerInfo.status == 1 else "🔴 Offline"
            )

        table.add_row(
            app.name,
            app.appId,
            app.description,
            server_url,
            server_status,
            app.createdAt.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)
