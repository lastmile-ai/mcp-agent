"""Deploy command for MCP Agent Cloud CLI.

This module provides the deploy_config function which processes configuration files
with secret tags and transforms them into deployment-ready configurations with secret handles.
"""

import asyncio
from pathlib import Path
from typing import Optional

import typer

from mcp_agent_cloud.auth import load_api_key_credentials
from mcp_agent_cloud.config import settings
from mcp_agent_cloud.core.constants import DEFAULT_CACHE_DIR
from mcp_agent_cloud.secrets.processor import process_config_secrets
from mcp_agent_cloud.secrets.mock_client import MockSecretsClient
from mcp_agent_cloud.ux import (
    print_info,
    print_success,
    print_error,
)
from .wrangler_wrapper import wrangler_deploy


def _run_async(coro):
    """
    Simple helper to run an async coroutine from synchronous code.

    This properly handles the event loop setup in all contexts:
    - Normal application usage
    - Within tests that use pytest-asyncio
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # If we're already in an event loop (like in pytest-asyncio tests)
        if "cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        raise


def deploy_config(
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
        help="Path to write the transformed secrets file.",
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
        None,
        "--api-url",
        help="API base URL. Overrides MCP_API_BASE_URL environment variable.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key for authentication. Overrides MCP_API_KEY environment variable.",
    ),
) -> str:
    """Deploy an MCP agent using the specified configuration and secrets files.

    This function:
    1. Processes the secrets file, transforming secret tags to secret IDs
    2. Deploys the agent with the main configuration and transformed secrets

    Args:
        config_file: Path to the main configuration file
        secrets_file: Path to the secrets file to process
        secrets_output_file: Path to write the transformed secrets file
        no_secrets: Skip secrets processing
        no_prompt: Never prompt for missing values (fail instead)
        dry_run: Validate the deployment but don't actually deploy
        api_url: API base URL
        api_key: API key for authentication

    Returns:
        Path to the main configuration file
    """
    # Display stylized deployment header
    from mcp_agent_cloud.ux import print_deployment_header

    print_deployment_header(config_file, secrets_file, dry_run)

    # Track the path to the configuration to use for deployment
    deployment_config_path = str(config_file)

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

        # Process secrets file
        if not no_secrets:
            # Process secrets file
            print_info("Processing secrets file...")
            secrets_transformed_path = (
                secrets_output_file or f"{secrets_file}.transformed.yaml"
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
                    secrets_context = _run_async(
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
                # Use the real API client
                secrets_context = _run_async(
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

            wrangler_deploy(api_key=effective_api_key)
        else:
            print_info("Dry run - skipping actual deployment.")

        # Final success message
        print_success("Deployment preparation completed successfully!")
        return deployment_config_path

    except Exception as e:
        print_error(f"{str(e)}")
        if settings.VERBOSE:
            import traceback

            typer.echo(traceback.format_exc())
        raise typer.Exit(1)
