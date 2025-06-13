"""Deploy command for MCP Agent Cloud CLI.

This module provides the deploy_config function which processes configuration files
with secret tags and transforms them into deployment-ready configurations with secret handles.
"""

from pathlib import Path
from typing import Optional

import typer

from mcp_agent_cloud.auth import load_api_key_credentials
from mcp_agent_cloud.config import settings
from mcp_agent_cloud.core.api_client import UnauthenticatedError
from mcp_agent_cloud.core.constants import (
    ENV_API_BASE_URL,
    ENV_API_KEY,
)
from mcp_agent_cloud.core.utils import run_async
from mcp_agent_cloud.mcp_app.api_client import MCPAppClient
from mcp_agent_cloud.mcp_app.mock_client import MockMCPAppClient
from mcp_agent_cloud.secrets.processor import (
    process_config_secrets,
)
from mcp_agent_cloud.secrets.mock_client import MockSecretsClient
from mcp_agent_cloud.ux import (
    print_info,
    print_success,
    print_error,
)
from .wrangler_wrapper import wrangler_deploy


def deploy_config(
    app_name: str = typer.Argument(
        help="Name of the MCP App to deploy.",
    ),
    app_description: Optional[str] = typer.Option(
        None,
        "--app-description",
        "-d",
        help="Description of the MCP App being deployed.",
    ),
    secrets_file: Path = typer.Option(
        Path("mcp-agent.secrets.yaml"),
        "--secrets-file",
        "-s",
        help="Path to the input secrets YAML file.",
        exists=True,
        readable=True,
        dir_okay=False,
        resolve_path=True,
    ),
    config_file: Path = typer.Option(
        Path("mcp-agent.config.yaml"),
        "--config-file",
        "-c",
        help="Path to the main config YAML file.",
        exists=True,
        readable=True,
        dir_okay=False,
        resolve_path=True,
    ),
    secrets_output_file: Optional[Path] = typer.Option(
        None,
        "--secrets-output-file",
        help="Path to write the transformed secrets file. Defaults to mcp-agent.deployed.secrets.yaml",
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
    """Deploy an MCP agent using the specified configuration and secrets files.

    This function:
    1. Processes the secrets file, transforming secret tags to secret IDs
    2. Deploys the agent with the main configuration and transformed secrets

    Args:
        app_name: Name of the MCP App to deploy
        config_file: Path to the main configuration file
        secrets_file: Path to the secrets file to process
        secrets_output_file: Path to write the transformed secrets file
        no_secrets: Skip secrets processing
        no_prompt: Never prompt for missing values (fail instead)
        dry_run: Validate the deployment but don't actually deploy
        api_url: API base URL
        api_key: API key for authentication

    Returns:
        Newly-deployed MCP App ID
    """
    # Display stylized deployment header
    from mcp_agent_cloud.ux import print_deployment_header

    print_deployment_header(config_file, secrets_file, dry_run)

    try:
        # Validate API-related environment variables or parameters
        # Use the provided api_key
        provided_key = api_key

        effective_api_url = api_url or settings.API_BASE_URL
        effective_api_key = (
            provided_key or settings.API_KEY or load_api_key_credentials()
        )

        # Check for required API credentials - but only for real deployment
        if not dry_run:
            if not effective_api_url:
                print_error(
                    "MCP_API_BASE_URL environment variable or --api-url option must be set."
                )
                raise typer.Exit(1)
            if not effective_api_key:
                print_error(
                    "Must be logged in to deploy. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
                )
                raise typer.Exit(1)
            print_info(f"Using API at {effective_api_url}")

        else:
            # For dry run, we'll use mock values if not provided
            effective_api_url = (
                effective_api_url or "http://localhost:3000/api"
            )
            effective_api_key = effective_api_key or "mock-key-for-dry-run"
            print_info(f"Using mock API at {effective_api_url} (dry run)")

        if dry_run:
            # Use the mock api client in dry run mode
            print_info("Using MOCK APP API client for dry run")

            # Create the mock client
            mcp_app_client = MockMCPAppClient(
                api_url=effective_api_url, api_key=effective_api_key
            )
        else:
            mcp_app_client = MCPAppClient(
                api_url=effective_api_url, api_key=effective_api_key
            )

        # Look for an existing app ID for this app name
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
            print_error(
                "Invalid API key for deployment. Run 'mcp-agent login --force' or set MCP_API_KEY environment variable with new API key."
            )
            raise typer.Exit(1) from e
        except Exception as e:
            print_error(f"Error checking or creating app: {str(e)}")
            raise typer.Exit(1)

        # Process secrets file
        if not no_secrets:
            # Process secrets file
            print_info("Processing secrets file...")
            if secrets_output_file:
                secrets_transformed_path = secrets_output_file
            else:
                # Use a more consistent naming convention with .deployed.secrets.yaml suffix
                secrets_transformed_path = Path(
                    f"{secrets_file.stem.split('.')[0]}.deployed.secrets.yaml"
                )
                print_info(
                    f"Using default output path: {secrets_transformed_path}"
                )

            if dry_run:
                # Use the mock client in dry run mode
                print_info("Using MOCK Secrets API client for dry run")

                # Create the mock client
                mock_client = MockSecretsClient(
                    api_url=effective_api_url, api_key=effective_api_key
                )

                # Process with the mock client
                try:
                    run_async(
                        process_config_secrets(
                            config_path=secrets_file,
                            output_path=secrets_transformed_path,
                            client=mock_client,
                            non_interactive=non_interactive,
                        )
                    )
                except Exception as e:
                    print_error(
                        f"Error during secrets processing with mock client: {str(e)}"
                    )
                    raise
            else:
                # Use the real secrets API client
                run_async(
                    process_config_secrets(
                        config_path=secrets_file,
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

            # The secrets summary has already been shown by compare_configs,
            # so we don't need to show stats again

        else:
            print_info("Skipping secrets processing...")

        # Deploy agent
        if not dry_run:
            from rich.panel import Panel
            from mcp_agent_cloud.ux import console

            console.print(
                Panel(
                    "Ready to deploy MCP Agent with processed configuration",
                    title="Deployment Ready",
                    border_style="green",
                )
            )

            source_uri = wrangler_deploy(
                app_id=app_id, api_key=effective_api_key
            )

            # Deploy the app using the MCP App API
            print_info("Deploying MCP App bundle...")
            try:
                app = run_async(
                    mcp_app_client.deploy_app(
                        app_id=app_id,
                        source_uri=source_uri,
                    )
                )
                print_success("✅ MCP App deployed successfully!")
                print_info(f"App ID: {app_id}")

                if app.appServerInfo:
                    status = (
                        "ONLINE"
                        if app.appServerInfo.status == 1
                        else "OFFLINE"
                    )
                    print_info(f"App URL: {app.appServerInfo.serverUrl}")
                    print_info(f"App Status: {status}")
                return app_id
            except Exception as e:
                print_error(f"❌ Deployment failed: {str(e)}")
                raise typer.Exit(1)

        else:
            print_info("Dry run - skipping actual deployment.")
            print_success("Deployment preparation completed successfully!")
            return app_id

    except Exception as e:
        print_error(f"{str(e)}")
        if settings.VERBOSE:
            import traceback

            typer.echo(traceback.format_exc())
        raise typer.Exit(1)
