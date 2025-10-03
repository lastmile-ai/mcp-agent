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
from ...utils import resolve_server
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import (
    MCPAppClient,
    MCPAppConfiguration,
)
from mcp_agent.cli.utils.ux import print_error, print_info, print_success


def delete_app(
    app_id_or_url: str = typer.Option(
        None,
        "--id",
        "-i",
        help="ID or server URL of the app or app configuration to delete.",
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
    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in to delete. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
        )

    client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    if not app_id_or_url:
        raise CLIError(
            "You must provide an app ID, app config ID, or server URL to delete."
        )

    # The ID could be either an app ID or an app configuration ID. Use the prefix to parse it.
    id_type = "app"
    id_to_delete = None
    try:
        app_or_config = resolve_server(client, app_id_or_url)

        if isinstance(app_or_config, MCPAppConfiguration):
            id_to_delete = app_or_config.appConfigurationId
            id_type = "app configuration"
        else:
            id_to_delete = app_or_config.appId
            id_type = "app"

    except Exception as e:
        raise CLIError(
            f"Error retrieving app or config with ID or URL {app_id_or_url}: {str(e)}"
        ) from e

    if not force:
        confirmation = typer.confirm(
            f"Are you sure you want to delete the {id_type} with ID '{id_to_delete}'? This action cannot be undone.",
            default=False,
        )
        if not confirmation:
            print_info("Deletion cancelled.")
            raise typer.Exit(0)

    if dry_run:
        try:
            # Just check that the viewer can delete the app/config without actually doing it
            can_delete = run_async(
                client.can_delete_app(id_to_delete)
                if id_type == "app"
                else client.can_delete_app_configuration(id_to_delete)
            )
            if can_delete:
                print_success(
                    f"[Dry Run] Would delete {id_type} with ID '{id_to_delete}' if run without --dry-run flag."
                )
            else:
                print_error(
                    f"[Dry Run] Cannot delete {id_type} with ID '{id_to_delete}'. Check permissions or if it exists."
                )
            return
        except Exception as e:
            raise CLIError(f"Error during dry run: {str(e)}") from e

    try:
        run_async(
            client.delete_app(id_to_delete)
            if id_type == "app"
            else client.delete_app_configuration(id_to_delete)
        )

        print_success(f"Successfully deleted the {id_type} with ID '{id_to_delete}'.")

    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
        ) from e
    except Exception as e:
        raise CLIError(f"Error deleting {id_type}: {str(e)}") from e
