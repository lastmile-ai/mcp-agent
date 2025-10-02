import asyncio
from typing import List, Optional

import typer
from rich.panel import Panel

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
from mcp_agent.cli.utils.ux import console, print_info


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
            console.print("\n[bold blue]📦 Deployed MCP Apps (0)[/bold blue]")
            print_info("No deployed apps found.")

        console.print("\n" + "─" * 80 + "\n")

        if list_app_configs_res.appConfigurations:
            num_configs = list_app_configs_res.totalCount or len(
                list_app_configs_res.appConfigurations
            )
            print_info(f"Found {num_configs} configured app(s):")
            print_app_configs(list_app_configs_res.appConfigurations)
        else:
            console.print("\n[bold blue]⚙️  Configured MCP Apps (0)[/bold blue]")
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
    """Print a list of deployed apps in a clean, copyable format."""
    console.print(f"\n[bold blue]📦 Deployed MCP Apps ({len(apps)})[/bold blue]")

    for i, app in enumerate(apps):
        if i > 0:
            console.print()

        status = _server_status_text(
            app.appServerInfo.status
            if app.appServerInfo
            else "APP_SERVER_STATUS_OFFLINE"
        )

        console.print(f"[bold cyan]{app.name or 'Unnamed'}[/bold cyan] {status}")
        console.print(f"  App ID: {app.appId}")

        if app.appServerInfo and app.appServerInfo.serverUrl:
            console.print(f"  Server: {app.appServerInfo.serverUrl}")

        if app.description:
            console.print(f"  Description: {app.description}")

        console.print(f"  Created: {app.createdAt.strftime('%Y-%m-%d %H:%M:%S')}")
        meta = getattr(app, "deploymentMetadata", None)
        summary = _format_deploy_meta(meta)
        if summary:
            console.print(f"  Metadata: {summary}")


def print_app_configs(app_configs: List[MCPAppConfiguration]) -> None:
    """Print a list of configured apps in a clean, copyable format."""
    console.print(
        f"\n[bold blue]⚙️  Configured MCP Apps ({len(app_configs)})[/bold blue]"
    )

    for i, config in enumerate(app_configs):
        if i > 0:
            console.print()

        status = _server_status_text(
            config.appServerInfo.status
            if config.appServerInfo
            else "APP_SERVER_STATUS_OFFLINE"
        )

        console.print(
            f"[bold cyan]{config.app.name if config.app else 'Unnamed'}[/bold cyan] {status}"
        )
        console.print(f"  Config ID: {config.appConfigurationId}")

        if config.app:
            console.print(f"  App ID: {config.app.appId}")
            if config.app.description:
                console.print(f"  Description: {config.app.description}")

        if config.appServerInfo and config.appServerInfo.serverUrl:
            console.print(f"  Server: {config.appServerInfo.serverUrl}")

        if config.createdAt:
            console.print(
                f"  Created: {config.createdAt.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        meta = (
            getattr(config.app, "deploymentMetadata", None)
            if getattr(config, "app", None)
            else None
        )
        summary = _format_deploy_meta(meta)
        if summary:
            console.print(f"  Metadata: {summary}")


def _server_status_text(status: str, is_last_row: bool = False):
    """Convert server status code to emoji."""
    if status == "APP_SERVER_STATUS_ONLINE":
        return "[green]🟢 Online[/green]"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return "[red]🔴 Offline[/red]"
    else:
        return "❓ Unknown"


def _format_deploy_meta(meta):
    try:
        if meta is None:
            return None
        if isinstance(meta, str):
            import json as _json

            try:
                meta = _json.loads(meta)
            except Exception:
                return None
        if not isinstance(meta, dict):
            return None

        source = meta.get("source")
        if source == "git" or ("commit" in meta or "short" in meta):
            short = meta.get("short") or (meta.get("commit") or "")[:7]
            branch = meta.get("branch")
            dirty = meta.get("dirty")
            details = []
            if branch:
                details.append(branch)
            if dirty is True:
                details.append("dirty")
            elif dirty is False:
                details.append("clean")
            base = short or "unknown"
            return f"{base} ({', '.join(details)})" if details else base

        fp = meta.get("fingerprint") or meta.get("workspace_fingerprint")
        if fp:
            return f"workspace {str(fp)[:12]}"
        return None
    except Exception:
        return None
