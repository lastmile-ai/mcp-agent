from typing import Optional

import typer
from mcp_agent_cloud.auth import load_api_key_credentials
from mcp_agent_cloud.config import settings
from mcp_agent_cloud.core.api_client import UnauthenticatedError
from mcp_agent_cloud.core.constants import ENV_API_BASE_URL, ENV_API_KEY
from mcp_agent_cloud.core.utils import run_async
from mcp_agent_cloud.mcp_app.api_client import (
    APP_CONFIG_ID_PREFIX,
    APP_ID_PREFIX,
    MCPAppClient,
)
from mcp_agent_cloud.ux import print_error, print_info, print_success


def delete_app(
    app_id: str = typer.Option(
        None,
        "--id",
        "-i",
        help="ID of the app or app configuration to delete.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force delete the app or app configuration without confirmation.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate the deletion but don't actually delete.",
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
    """Delete an MCP App or App Configuration by ID."""
    effective_api_key = (
        api_key or settings.API_KEY or load_api_key_credentials()
    )

    if not effective_api_key:
        print_error(
            "Must be logged in to delete. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
        )
        raise typer.Exit(1)

    client = MCPAppClient(api_url=api_url, api_key=effective_api_key)

    if not app_id:
        print_error("You must provide an app ID or app config ID to delete.")
        raise typer.Exit(1)

    # The ID could be either an app ID or an app configuration ID. Use the prefix to parse it.
    id_type = "app"
    if app_id.startswith(APP_ID_PREFIX):
        id_type = "app"
    elif app_id.startswith(APP_CONFIG_ID_PREFIX):
        id_type = "app configuration"
    else:
        print_error(
            f"Invalid ID format. ID must start with '{APP_ID_PREFIX}' for apps or '{APP_CONFIG_ID_PREFIX}' for app configurations."
        )
        raise typer.Exit(1)

    if not force:
        confirmation = typer.confirm(
            f"Are you sure you want to delete the {id_type} with ID '{app_id}'? This action cannot be undone.",
            default=False,
        )
        if not confirmation:
            print_info("Deletion cancelled.")
            raise typer.Exit(0)

    if dry_run:
        try:
            # Just check that the viewer can delete the app/config without actually doing it
            can_delete = run_async(
                client.can_delete_app(app_id)
                if id_type == "app"
                else client.can_delete_app_configuration(app_id)
            )
            if can_delete:
                print_success(
                    f"[Dry Run] Would delete {id_type} with ID '{app_id}' if run without --dry-run flag."
                )
            else:
                print_error(
                    f"[Dry Run] Cannot delete {id_type} with ID '{app_id}'. Check permissions or if it exists."
                )
            return
        except Exception as e:
            print_error(f"Error during dry run: {str(e)}")
            raise typer.Exit(1)

    try:
        run_async(
            client.delete_app(app_id)
            if id_type == "app"
            else client.delete_app_configuration(app_id)
        )

        print_success(
            f"Successfully deleted the {id_type} with ID '{app_id}'."
        )

    except UnauthenticatedError as e:
        print_error(
            "Invalid API key. Run 'mcp-agent login --force' or set MCP_API_KEY environment variable with new API key."
        )
        raise typer.Exit(1) from e
    except Exception as e:
        print_error(f"Error deleting {id_type}: {str(e)}")
        raise typer.Exit(1)
