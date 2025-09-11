"""Deploy command for MCP Agent Cloud CLI.

This module provides the deploy_config function which processes configuration files
with secret tags and transforms them into deployment-ready configurations with secret handles.
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
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPAppClient
from mcp_agent.cli.mcp_app.mock_client import MockMCPAppClient
from mcp_agent.cli.secrets.mock_client import MockSecretsClient
from mcp_agent.cli.secrets.processor import (
    process_config_secrets,
)
from mcp_agent.cli.utils.ux import (
    console,
    print_deployment_header,
    print_info,
    print_success,
)

from .wrangler_wrapper import wrangler_deploy


def deploy_config(
    ctx: typer.Context,
    app_name: Optional[str] = typer.Argument(
        None,
        help="Name of the MCP App to deploy.",
    ),
    app_description: Optional[str] = typer.Option(
        None,
        "--app-description",
        "-d",
        help="Description of the MCP App being deployed.",
    ),
    config_dir: Path = typer.Option(
        Path(""),
        "--config-dir",
        "-c",
        help="Path to the directory containing the app config and app files.",
        exists=True,
        readable=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    no_secrets: bool = typer.Option(
        False,
        "--no-secrets",
        help="Skip secrets processing.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Fail if secrets require prompting, do not prompt.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate the deployment but don't actually deploy.",
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
    """Deploy an MCP agent using the specified configuration.

    An MCP App is deployed from bundling the code at the specified config directory.
    This directory must contain an 'mcp_agent.config.yaml' at its root. If secrets are required
    (i.e. `no_secrets` is not set), a secrets file named 'mcp_agent.secrets.yaml' must also be present.
    The secrets file is processed to replace secret tags with secret handles before deployment and that transformed
    file is included in the deployment bundle in place of the original secrets file.

    Args:
        app_name: Name of the MCP App to deploy
        app_description: Description of the MCP App being deployed
        config_dir: Path to the directory containing the app configuration files
        no_secrets: Skip secrets processing
        no_prompt: Never prompt for missing values (fail instead)
        dry_run: Validate the deployment but don't actually deploy
        api_url: API base URL
        api_key: API key for authentication

    Returns:
        Newly-deployed MCP App ID
    """
    # Show help if no app_name is provided
    if app_name is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    # Validate config directory and required files
    config_file, secrets_file = get_config_files(config_dir, no_secrets)
    print_deployment_header(config_file, secrets_file, dry_run)

    try:
        provided_key = api_key
        effective_api_url = api_url or settings.API_BASE_URL
        effective_api_key = (
            provided_key or settings.API_KEY or load_api_key_credentials()
        )

        if dry_run:
            # For dry run, we'll use mock values if not provided
            effective_api_url = effective_api_url or DEFAULT_API_BASE_URL
            effective_api_key = effective_api_key or "mock-key-for-dry-run"

            print_info("Using MOCK APP API client for dry run")
            mcp_app_client: Union[MockMCPAppClient, MCPAppClient] = MockMCPAppClient(
                api_url=effective_api_url, api_key=effective_api_key
            )

        else:
            if not effective_api_url:
                raise CLIError(
                    "MCP_API_BASE_URL environment variable or --api-url option must be set."
                )
            if not effective_api_key:
                raise CLIError(
                    "Must be logged in to deploy. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
                )
            print_info(f"Using API at {effective_api_url}")

            mcp_app_client = MCPAppClient(
                api_url=effective_api_url, api_key=effective_api_key
            )

        print_info(f"Checking for existing app ID for '{app_name}'...")
        try:
            app_id = run_async(mcp_app_client.get_app_id_by_name(app_name))
            if not app_id:
                print_info(
                    f"No existing app found with name '{app_name}'. Creating a new app..."
                )
                app = run_async(
                    mcp_app_client.create_app(
                        name=app_name, description=app_description
                    )
                )
                app_id = app.appId
                print_success(f"Created new app with ID: {app_id}")
            else:
                print_success(
                    f"Found existing app with ID: {app_id} for name '{app_name}'"
                )
        except UnauthenticatedError as e:
            raise CLIError(
                "Invalid API key for deployment. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
            ) from e
        except Exception as e:
            raise CLIError(f"Error checking or creating app: {str(e)}")

        secrets_transformed_path = None
        if secrets_file:
            print_info("Processing secrets file...")
            secrets_transformed_path = Path(
                f"{config_dir}/{MCP_DEPLOYED_SECRETS_FILENAME}"
            )

            if dry_run:
                print_info("Using MOCK Secrets API client for dry run")
                mock_client = MockSecretsClient(
                    api_url=effective_api_url, api_key=effective_api_key
                )

                try:
                    run_async(
                        process_config_secrets(
                            input_path=secrets_file,
                            output_path=secrets_transformed_path,
                            client=mock_client,
                            non_interactive=non_interactive,
                        )
                    )
                except Exception as e:
                    raise CLIError(
                        f"Error during secrets processing with mock client: {str(e)}"
                    ) from e
            else:
                # Use the real secrets API client
                run_async(
                    process_config_secrets(
                        input_path=secrets_file,
                        output_path=secrets_transformed_path,
                        api_url=effective_api_url,
                        api_key=effective_api_key,
                        non_interactive=non_interactive,
                    )
                )

            print_success("Secrets file processed successfully")
            print_info(
                f"Transformed secrets file written to {secrets_transformed_path}"
            )

        else:
            print_info("Skipping secrets processing...")

        if dry_run:
            print_info("Dry run - skipping actual deployment.")
            print_success("Deployment preparation completed successfully!")
            return app_id

        console.print(
            Panel(
                "Ready to deploy MCP Agent with processed configuration",
                title="Deployment Ready",
                border_style="green",
            )
        )

        wrangler_deploy(
            app_id=app_id,
            api_key=effective_api_key,
            project_dir=config_dir,
        )

        with Progress(
            SpinnerColumn(spinner_name="arrow3"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Deploying MCP App bundle...", total=None)

            try:
                assert isinstance(mcp_app_client, MCPAppClient)
                app = run_async(
                    mcp_app_client.deploy_app(
                        app_id=app_id,
                    )
                )
                progress.update(task, description="✅ MCP App deployed successfully!")
                print_info(f"App ID: {app_id}")

                if app.appServerInfo:
                    status = (
                        "ONLINE"
                        if app.appServerInfo.status == "APP_SERVER_STATUS_ONLINE"
                        else "OFFLINE"
                    )
                    print_info(f"App URL: {app.appServerInfo.serverUrl}")
                    print_info(f"App Status: {status}")
                return app_id

            except Exception as e:
                progress.update(task, description="❌ Deployment failed")
                raise e

    except Exception as e:
        if settings.VERBOSE:
            import traceback

            typer.echo(traceback.format_exc())
        raise CLIError(f"Deployment failed: {str(e)}") from e


def get_config_files(config_dir: Path, no_secrets: bool) -> tuple[Path, Optional[Path]]:
    """Get the configuration and secrets files from the configuration directory.

    Args:
        config_dir: Directory containing the configuration files
        no_secrets: Whether to skip secrets processing

    Returns:
        Tuple of (config_file_path, secrets_file_path or None)
    """

    config_file = config_dir / MCP_CONFIG_FILENAME
    if not config_file.exists():
        raise CLIError(
            f"Configuration file '{MCP_CONFIG_FILENAME}' not found in {config_dir}"
        )

    secrets_file_path = config_dir / MCP_SECRETS_FILENAME
    secrets_file: Optional[Path] = None

    if no_secrets:
        if secrets_file_path.exists():
            raise CLIError(
                f"Secrets file '{MCP_SECRETS_FILENAME}' found in {config_dir} but --no-secrets is specified. Remove the secrets file or omit --no-secrets."
            )
        secrets_file = None
    elif not secrets_file_path.exists():
        raise CLIError(
            f"Secrets file '{MCP_SECRETS_FILENAME}' not found in {config_dir}. Required unless --no-secrets is specified."
        )
    else:
        secrets_file = secrets_file_path

    return config_file, secrets_file
