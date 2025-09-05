"""Configure command for MCP Agent Cloud CLI.

This module provides the configure_app function which creates a new configuration of the app with
the required configuration parameters (e.g. user secrets).
"""

from pathlib import Path
from typing import Optional, Union

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
    MCP_CONFIGURED_SECRETS_FILENAME,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import (
    MCPAppClient,
)
from mcp_agent.cli.mcp_app.mock_client import MockMCPAppClient
from mcp_agent.cli.secrets.mock_client import MockSecretsClient
from mcp_agent.cli.secrets.processor import (
    configure_user_secrets,
)
from mcp_agent.cli.utils.ux import (
    console,
    print_configuration_header,
    print_info,
    print_success,
)


def configure_app(
    app_server_url: str = typer.Option(
        None,
        "--id",
        "-i",
        help="Server URL of the app to configure.",
    ),
    secrets_file: Optional[Path] = typer.Option(
        None,
        "--secrets-file",
        "-s",
        help="Path to a secrets.yaml file containing user secret IDs to use for configuring the app. If not provided, secrets will be prompted interactively.",
        exists=True,
        readable=True,
        dir_okay=False,
        resolve_path=True,
    ),
    secrets_output_file: Optional[Path] = typer.Option(
        None,
        "--secrets-output-file",
        "-o",
        help="Path to write prompted and tranformed secrets to. Defaults to mcp_agent.configured.secrets.yaml",
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate the configuration but don't store secrets.",
    ),
    params: bool = typer.Option(
        False,
        "--params",
        help="Show required parameters (user secrets) for the configuration process and exit.",
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
) -> str:
    """Configure an MCP app with the required params (e.g. user secrets).

    Args:
        app_server_url: Server URL of the MCP App to configure
        secrets_file: Path to an existing secrets file containing processed user secrets to use for configuring the app
        secrets_output_file: Path to write processed secrets to, if secrets are prompted. Defaults to mcp-agent.configured.secrets.yaml
        dry_run: Don't actually store secrets, just validate
        api_url: API base URL
        api_key: API key for authentication

    Returns:
        Configured app ID.
    """
    # Check what params the app requires (doubles as an access check)
    if not app_server_url:
        raise CLIError("You must provide a server URL to configure.")

    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()
    if not effective_api_key:
        raise CLIError(
            "Must be logged in to configure. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
        )

    client: Union[MockMCPAppClient, MCPAppClient]
    if dry_run:
        # Use the mock api client in dry run mode
        print_info("Using MOCK API client for dry run")
        client = MockMCPAppClient(
            api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
        )
    else:
        client = MCPAppClient(
            api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
        )

    # Cannot provide both secrets_file and secrets_output_file; either must be yaml files
    if secrets_file and secrets_output_file:
        raise CLIError(
            "Cannot provide both --secrets-file and --secrets-output-file options. Please specify only one."
        )
    elif secrets_file and not secrets_file.suffix == ".yaml":
        raise CLIError(
            "The --secrets-file must be a YAML file. Please provide a valid path."
        )
    elif secrets_output_file and not secrets_output_file.suffix == ".yaml":
        raise CLIError(
            "The --secrets-output-file must be a YAML file. Please provide a valid path."
        )

    required_params = []
    try:
        required_params = run_async(
            client.list_config_params(app_server_url=app_server_url)
        )
    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
        ) from e
    except Exception as e:
        raise CLIError(
            f"Failed to retrieve required secrets for app {app_server_url}: {e}"
        ) from e

    requires_secrets = len(required_params) > 0
    configured_secrets = {}

    if params:
        if requires_secrets:
            print_info(
                f"App {app_server_url} requires the following ({len(required_params)}) user secrets: {', '.join(required_params)}"
            )
        else:
            print_info(f"App {app_server_url} does not require any user secrets.")
        raise typer.Exit(0)

    if requires_secrets:
        if not secrets_file and secrets_output_file is None:
            # Set default output file if not specified
            secrets_output_file = Path(MCP_CONFIGURED_SECRETS_FILENAME)
            print_info(f"Using default output path: {secrets_output_file}")

        print_configuration_header(secrets_file, secrets_output_file, dry_run)

        print_info(
            f"App {app_server_url} requires the following ({len(required_params)}) user secrets: {', '.join(required_params)}"
        )

        try:
            print_info("Processing user secrets...")

            if dry_run:
                # Use the mock client in dry run mode
                print_info("Using MOCK Secrets API client for dry run")

                # Create the mock client
                mock_client = MockSecretsClient(
                    api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
                )

                # Process with the mock client
                try:
                    configured_secrets = run_async(
                        configure_user_secrets(
                            required_secrets=required_params,
                            config_path=secrets_file,
                            output_path=secrets_output_file,
                            client=mock_client,
                        )
                    )
                except Exception as e:
                    raise CLIError(
                        f"Error during secrets processing with mock client: {str(e)}"
                    ) from e
            else:
                # Use the real API client
                configured_secrets = run_async(
                    configure_user_secrets(
                        required_secrets=required_params,
                        config_path=secrets_file,
                        output_path=secrets_output_file,
                        api_url=api_url,
                        api_key=effective_api_key,
                    )
                )

            print_success("User secrets processed successfully")

        except Exception as e:
            if settings.VERBOSE:
                import traceback

                typer.echo(traceback.format_exc())
            raise CLIError(f"{str(e)}") from e

    else:
        print_info(f"App {app_server_url} does not require any parameters.")
        if secrets_file:
            raise CLIError(
                f"App {app_server_url} does not require any parameters, but a secrets file was provided: {secrets_file}"
            )

    if dry_run:
        print_success("Configuration completed in dry run mode.")
        return "dry-run-app-configuration-id"

    # Finally, configure the app for the user
    with Progress(
        SpinnerColumn(spinner_name="arrow3"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task("Configuring MCP App...", total=None)

        try:
            config = run_async(
                client.configure_app(
                    app_server_url=app_server_url, config_params=configured_secrets
                )
            )
            progress.update(task, description="✅ MCP App configured successfully!")
            console.print(
                Panel(
                    f"Configured App ID: [cyan]{config.appConfigurationId}[/cyan]\n"
                    f"Configured App Server URL: [cyan]{config.appServerInfo.serverUrl if config.appServerInfo else ''}[/cyan]",
                    title="Configuration Complete",
                    border_style="green",
                )
            )

            return config.appConfigurationId

        except Exception as e:
            progress.update(task, description="❌ MCP App configuration failed")
            raise CLIError(f"Failed to configure app {app_server_url}: {str(e)}") from e
