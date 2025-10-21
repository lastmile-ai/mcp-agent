from typing import Optional

import typer

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
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppClient, MCPAppConfiguration
from mcp_agent.cli.utils.ux import print_info, print_success
from ...utils import resolve_server


def update_app(
    app_id_or_name: str = typer.Argument(
        ...,
        help="ID, server URL, configuration ID, or name of the app to update.",
        show_default=False,
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Set a new name for the app.",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Set a new description for the app. Use an empty string to clear it.",
    ),
    unauthenticated_access: Optional[bool] = typer.Option(
        None,
        "--no-auth/--auth",
        help=(
            "Allow unauthenticated access to the app server (--no-auth) or require authentication (--auth). "
            "If omitted, the current setting is preserved."
        ),
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
    """Update metadata or authentication settings for a deployed MCP App."""
    if name is None and description is None and unauthenticated_access is None:
        raise CLIError(
            "Specify at least one of --name, --description, or --no-auth/--auth to update.",
            retriable=False,
        )

    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in to update an app. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option.",
            retriable=False,
        )

    client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    try:
        resolved = resolve_server(client, app_id_or_name)

        if isinstance(resolved, MCPAppConfiguration):
            if not resolved.app:
                raise CLIError(
                    "Could not resolve the underlying app for the configuration provided."
                )
            target_app: MCPApp = resolved.app
        else:
            target_app = resolved

        updated_app = run_async(
            client.update_app(
                app_id=target_app.appId,
                name=name,
                description=description,
                unauthenticated_access=unauthenticated_access,
            )
        )

        short_id = f"{updated_app.appId[:8]}…"
        print_success(
            f"Updated app '{updated_app.name or target_app.name}' (ID: `{short_id}`)"
        )

        if updated_app.description is not None:
            desc_text = updated_app.description or "(cleared)"
            print_info(f"Description: {desc_text}")

        app_server_info = updated_app.appServerInfo
        if app_server_info and app_server_info.serverUrl:
            print_info(f"Server URL: {app_server_info.serverUrl}")
            if app_server_info.unauthenticatedAccess is not None:
                auth_msg = (
                    "Unauthenticated access allowed"
                    if app_server_info.unauthenticatedAccess
                    else "Authentication required"
                )
                print_info(f"Authentication: {auth_msg}")

    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
        ) from e
    except CLIError:
        raise
    except Exception as e:
        raise CLIError(f"Error updating app: {str(e)}") from e
