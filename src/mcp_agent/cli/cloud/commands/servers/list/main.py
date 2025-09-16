import asyncio
import json
from typing import List, Optional, Union

import typer
import yaml
from rich.panel import Panel

from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppConfiguration
from ...utils import (
    setup_authenticated_client,
    validate_output_format,
    handle_server_api_errors,
    clean_server_status,
)
from mcp_agent.cli.utils.ux import console, print_info
from datetime import datetime


@handle_server_api_errors
def list_servers(
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Maximum number of results to return"
    ),
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Filter by name, description, or status (case-insensitive)",
    ),
    sort_by: Optional[str] = typer.Option(
        None,
        "--sort-by",
        help="Sort by field: name, created, status (prefix with - for reverse)",
    ),
    format: Optional[str] = typer.Option(
        "text", "--format", help="Output format (text|json|yaml)"
    ),
) -> None:
    """List MCP Servers with optional filtering and sorting.

    Examples:

        mcp-agent cloud servers list --filter api

        mcp-agent cloud servers list --sort-by -created

        mcp-agent cloud servers list --filter active --sort-by name

        mcp-agent cloud servers list --filter production --format json
    """
    validate_output_format(format)
    client = setup_authenticated_client()

    # Use limit or default
    max_results = limit or 100

    async def parallel_requests():
        return await asyncio.gather(
            client.list_apps(max_results=max_results),
            client.list_app_configurations(max_results=max_results),
        )

    list_apps_res, list_app_configs_res = run_async(parallel_requests())

    # Apply client-side filtering and sorting
    filtered_deployed = (
        _apply_filter(list_apps_res.apps, filter) if filter else list_apps_res.apps
    )
    filtered_configured = (
        _apply_filter(list_app_configs_res.appConfigurations, filter)
        if filter
        else list_app_configs_res.appConfigurations
    )

    sorted_deployed = (
        _apply_sort(filtered_deployed, sort_by) if sort_by else filtered_deployed
    )
    sorted_configured = (
        _apply_sort(filtered_configured, sort_by) if sort_by else filtered_configured
    )

    if format == "json":
        _print_servers_json(sorted_deployed, sorted_configured)
    elif format == "yaml":
        _print_servers_yaml(sorted_deployed, sorted_configured)
    else:
        _print_servers_text(sorted_deployed, sorted_configured, filter, sort_by)


def _apply_filter(
    servers: List[Union[MCPApp, MCPAppConfiguration]], filter_expr: str
) -> List[Union[MCPApp, MCPAppConfiguration]]:
    """Apply client-side filtering to servers."""
    if not filter_expr:
        return servers

    filtered_servers = []
    # Support basic filtering by name, status, description
    filter_lower = filter_expr.lower()

    for server in servers:
        # Get server attributes for filtering
        try:
            if isinstance(server, MCPApp):
                name = server.name or ""
                description = server.description or ""
                status = (
                    server.appServerInfo.status
                    if server.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                )
            elif hasattr(server, "app"):  # MCPAppConfiguration
                name = server.app.name if server.app else ""
                description = server.app.description if server.app else ""
                status = (
                    server.appServerInfo.status
                    if server.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                )
            else:  # Fallback for other types (like test mocks)
                name = getattr(server, "name", "") or ""
                description = getattr(server, "description", "") or ""
                server_info = getattr(server, "appServerInfo", None)
                status = (
                    server_info.status if server_info else "APP_SERVER_STATUS_OFFLINE"
                )
        except Exception:
            # Skip servers that can't be processed
            continue

        # Clean status for filtering
        clean_status = clean_server_status(status).lower()

        # Check if filter matches name, description, or status
        if (
            filter_lower in name.lower()
            or filter_lower in description.lower()
            or filter_lower in clean_status
        ):
            filtered_servers.append(server)

    return filtered_servers


def _apply_sort(
    servers: List[Union[MCPApp, MCPAppConfiguration]], sort_field: str
) -> List[Union[MCPApp, MCPAppConfiguration]]:
    """Apply client-side sorting to servers."""
    if not sort_field:
        return servers

    # Normalize sort field
    sort_field_lower = sort_field.lower()
    reverse = False

    # Support reverse sorting with - prefix
    if sort_field_lower.startswith("-"):
        reverse = True
        sort_field_lower = sort_field_lower[1:]

    def get_sort_key(server):
        try:
            if isinstance(server, MCPApp):
                name = server.name or ""
                created_at = server.createdAt
                status = (
                    server.appServerInfo.status
                    if server.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                )
            elif hasattr(server, "app"):  # MCPAppConfiguration
                name = server.app.name if server.app else ""
                created_at = server.createdAt
                status = (
                    server.appServerInfo.status
                    if server.appServerInfo
                    else "APP_SERVER_STATUS_OFFLINE"
                )
            else:  # Fallback for other types (like test mocks)
                name = getattr(server, "name", "") or ""
                created_at = getattr(server, "createdAt", None)
                server_info = getattr(server, "appServerInfo", None)
                status = (
                    server_info.status if server_info else "APP_SERVER_STATUS_OFFLINE"
                )
        except Exception:
            # Return default values for sorting if server can't be processed
            name = ""
            created_at = None
            status = "APP_SERVER_STATUS_OFFLINE"

        if sort_field_lower == "name":
            return name.lower()
        elif sort_field_lower in ["created", "created_at", "date"]:
            return created_at or datetime.min.replace(
                tzinfo=None if created_at is None else created_at.tzinfo
            )
        elif sort_field_lower == "status":
            return clean_server_status(status).lower()
        else:
            # Default to name if sort field not recognized
            return name.lower()

    try:
        return sorted(servers, key=get_sort_key, reverse=reverse)
    except Exception:
        # If sorting fails, return original list
        return servers


def _print_servers_text(
    deployed_servers: List[MCPApp],
    configured_servers: List[MCPAppConfiguration],
    filter_param: Optional[str],
    sort_by: Optional[str],
) -> None:
    """Print servers in text format."""
    print_info_header()

    # Display deployed servers
    if deployed_servers:
        num_servers = len(deployed_servers)
        print_info(f"Found {num_servers} deployed server(s):")
        print_servers(deployed_servers)
    else:
        console.print("\n[bold blue]🖥️  Deployed MCP Servers (0)[/bold blue]")
        print_info("No deployed servers found.")

    console.print("\n" + "─" * 80 + "\n")

    # Display configured servers
    if configured_servers:
        num_configs = len(configured_servers)
        print_info(f"Found {num_configs} configured server(s):")
        print_server_configs(configured_servers)
    else:
        console.print("\n[bold blue]⚙️  Configured MCP Servers (0)[/bold blue]")
        print_info("No configured servers found.")

    if filter_param or sort_by:
        console.print(
            f"\n[dim]Applied filters: filter={filter_param or 'None'}, sort-by={sort_by or 'None'}[/dim]"
        )
        filter_desc = f"filter='{filter_param}'" if filter_param else "filter=None"
        sort_desc = f"sort-by='{sort_by}'" if sort_by else "sort-by=None"
        print_info(
            f"Client-side {filter_desc}, {sort_desc}. Sort fields: name, created, status (-prefix for reverse)."
        )


def _print_servers_json(
    deployed_servers: List[MCPApp], configured_servers: List[MCPAppConfiguration]
) -> None:
    """Print servers in JSON format."""
    deployed_data = [_server_to_dict(server) for server in deployed_servers]
    configured_data = [_server_config_to_dict(config) for config in configured_servers]

    output = {"deployed_servers": deployed_data, "configured_servers": configured_data}
    print(json.dumps(output, indent=2, default=str))


def _print_servers_yaml(
    deployed_servers: List[MCPApp], configured_servers: List[MCPAppConfiguration]
) -> None:
    """Print servers in YAML format."""
    deployed_data = [_server_to_dict(server) for server in deployed_servers]
    configured_data = [_server_config_to_dict(config) for config in configured_servers]

    output = {"deployed_servers": deployed_data, "configured_servers": configured_data}
    print(yaml.dump(output, default_flow_style=False))


def _server_to_dict(server: MCPApp) -> dict:
    """Convert MCPApp to dictionary."""
    status_raw = (
        server.appServerInfo.status
        if server.appServerInfo
        else "APP_SERVER_STATUS_OFFLINE"
    )
    return {
        "id": server.appId,
        "name": server.name or "Unnamed",
        "description": server.description,
        "status": clean_server_status(status_raw),
        "server_url": server.appServerInfo.serverUrl if server.appServerInfo else None,
        "creator_id": server.creatorId,
        "created_at": server.createdAt.isoformat() if server.createdAt else None,
        "type": "deployed",
        "deployment_metadata": getattr(server, "deploymentMetadata", None),
    }


def _server_config_to_dict(config: MCPAppConfiguration) -> dict:
    """Convert MCPAppConfiguration to dictionary."""
    status_raw = (
        config.appServerInfo.status
        if config.appServerInfo
        else "APP_SERVER_STATUS_OFFLINE"
    )
    return {
        "config_id": config.appConfigurationId,
        "app_id": config.app.appId if config.app else None,
        "name": config.app.name if config.app else "Unnamed",
        "description": config.app.description if config.app else None,
        "status": clean_server_status(status_raw),
        "server_url": config.appServerInfo.serverUrl if config.appServerInfo else None,
        "creator_id": config.creatorId,
        "created_at": config.createdAt.isoformat() if config.createdAt else None,
        "type": "configured",
        "deployment_metadata": getattr(config.app, "deploymentMetadata", None)
        if getattr(config, "app", None)
        else None,
    }


def print_info_header() -> None:
    """Print a styled header explaining the following tables"""
    console.print(
        Panel(
            "Deployed Servers: [cyan]MCP Servers which you have bundled and deployed, as a developer[/cyan]\n"
            "Configured Servers: [cyan]MCP Servers which you have configured to use with your MCP clients[/cyan]",
            title="MCP Servers",
            border_style="blue",
            expand=False,
        )
    )


def print_servers(servers: List[MCPApp]) -> None:
    """Print a list of deployed servers in a clean, copyable format."""
    console.print(f"\n[bold blue]🖥️  Deployed MCP Servers ({len(servers)})[/bold blue]")

    for i, server in enumerate(servers):
        if i > 0:
            console.print()

        status = _server_status_text(
            server.appServerInfo.status
            if server.appServerInfo
            else "APP_SERVER_STATUS_OFFLINE"
        )

        console.print(f"[bold cyan]{server.name or 'Unnamed'}[/bold cyan] {status}")
        console.print(f"  App ID: {server.appId}")

        if server.appServerInfo and server.appServerInfo.serverUrl:
            console.print(f"  Server URL: {server.appServerInfo.serverUrl}")

        if server.description:
            console.print(f"  Description: {server.description}")

        console.print(f"  Created: {server.createdAt.strftime('%Y-%m-%d %H:%M:%S')}")

        meta = getattr(server, "deploymentMetadata", None)
        summary = _format_deploy_meta(meta)
        if summary:
            console.print(f"  Metadata: {summary}")


def print_server_configs(server_configs: List[MCPAppConfiguration]) -> None:
    """Print a list of configured servers in a clean, copyable format."""
    console.print(
        f"\n[bold blue]⚙️  Configured MCP Servers ({len(server_configs)})[/bold blue]"
    )

    for i, config in enumerate(server_configs):
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
            console.print(f"  Server URL: {config.appServerInfo.serverUrl}")

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


def _server_status_text(status: str) -> str:
    """Convert server status code to emoji."""
    if status == "APP_SERVER_STATUS_ONLINE":
        return "[green]🟢 Active[/green]"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return "[red]🔴 Offline[/red]"
    else:
        return "❓ Unknown"


def _format_deploy_meta(meta) -> Optional[str]:
    """Return a one-line deployment summary if metadata is present.

    Accepts either a dict or a JSON string.
    """
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

        # workspace fallback
        fp = meta.get("fingerprint") or meta.get("workspace_fingerprint")
        if fp:
            return f"workspace {str(fp)[:12]}"
        return None
    except Exception:
        return None
