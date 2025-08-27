import asyncio
from typing import List, Optional

import typer
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import (
    MCPApp,
    MCPAppClient,
    MCPAppConfiguration,
)
from mcp_agent.cli.ux import console, print_info


def list_apps(
    name_filter: str = typer.Option(None, "--name", "-n", help="Filter apps by name"),
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
    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in to list apps. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
        )

    client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    try:

        async def parallel_requests():
            return await asyncio.gather(
                client.list_apps(name_filter=name_filter, max_results=max_results),
                client.list_app_configurations(
                    name_filter=name_filter, max_results=max_results
                ),
            )

        list_apps_res, list_app_configs_res = run_async(parallel_requests())

        print_info_header()

        if list_apps_res.apps:
            num_apps = list_apps_res.totalCount or len(list_apps_res.apps)
            print_info(f"Found {num_apps} deployed app(s):")
            print_apps(list_apps_res.apps)
        else:
            print_info("No deployed apps found.")

        if list_app_configs_res.appConfigurations:
            num_configs = list_app_configs_res.totalCount or len(
                list_app_configs_res.appConfigurations
            )
            print_info(f"Found {num_configs} configured app(s):")
            print_app_configs(list_app_configs_res.appConfigurations)
        else:
            print_info("No configured apps found.")

    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
        ) from e
    except Exception as e:
        raise CLIError(f"Error listing apps: {str(e)}") from e


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
    table = Table(
        title="Deployed MCP Apps",
        expand=False,
        border_style="blue",
        padding=(0, 1),
    )

    table.add_column("Name", style="cyan", overflow="fold")
    table.add_column("ID", style="bright_blue", no_wrap=True)
    table.add_column("Description", style="cyan", overflow="fold")
    table.add_column("Server URL", style="bright_blue", no_wrap=True)
    table.add_column("Status", style="bright_blue", no_wrap=True)
    table.add_column("Created", style="cyan", overflow="fold")

    for idx, app in enumerate(apps):
        is_last_row = idx == len(apps) - 1
        table.add_row(
            app.name,
            app.appId,
            app.description,
            app.appServerInfo.serverUrl if app.appServerInfo else "",
            _server_status_text(
                (
                    app.appServerInfo.status
                    if app.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                ),
                is_last_row,
            ),
            app.createdAt.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


def print_app_configs(app_configs: List[MCPAppConfiguration]) -> None:
    """Print a summary table of the app configuration information."""
    table = Table(title="Configured MCP Apps", expand=False, border_style="blue")

    table.add_column("Name", style="cyan", overflow="fold")
    table.add_column("ID", style="bright_blue", no_wrap=True)
    table.add_column("App ID", style="bright_blue", overflow="fold")
    table.add_column("Description", style="cyan", overflow="fold")
    table.add_column("Server URL", style="bright_blue", no_wrap=True)
    table.add_column("Status", style="bright_blue", no_wrap=True)
    table.add_column("Created", style="cyan", overflow="fold")

    for idx, config in enumerate(app_configs):
        is_last_row = idx == len(app_configs) - 1
        table.add_row(
            config.app.name if config.app else "",
            config.appConfigurationId,
            config.app.appId if config.app else "",
            config.app.description if config.app else "",
            config.appServerInfo.serverUrl if config.appServerInfo else "",
            _server_status_text(
                (
                    config.appServerInfo.status
                    if config.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                ),
                is_last_row=is_last_row,
            ),
            config.createdAt.strftime("%Y-%m-%d %H:%M:%S") if config.createdAt else "",
        )

    console.print(table)


def _server_status_text(status: str, is_last_row: bool = False):
    """Convert server status code to emoji."""
    if status == "APP_SERVER_STATUS_ONLINE":
        return "🟢 Online"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return Padding("🔴 Offline", (0, 0, 0 if is_last_row else 1, 0), style="red")
    else:
        return "❓ Unknown"
