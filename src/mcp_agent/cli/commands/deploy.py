"""Deploy command for MCP Agent Cloud CLI.

This module provides the deploy_config function which processes configuration files
with secret tags and transforms them into deployment-ready configurations with secret handles.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional, Union, Any

import typer

from ..config import settings
from ..secrets.processor import process_config_secrets
from ..secrets.mock_client import MockSecretsClient
from ..ux import print_info, print_success, print_warning, print_error


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
    config_file: Path = typer.Argument(
        ...,
        help="Path to the MCP agent configuration file.",
        exists=True,
        readable=True,
        dir_okay=False,
        resolve_path=True,
    ),
    secrets_file: Path = typer.Option(
        ...,
        "--secrets-file",
        "-s",
        help="Path to the secrets YAML file to process.",
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
    no_prompt: bool = typer.Option(
        False,
        "--no-prompt",
        help="Never prompt for missing values. Fail instead.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate the deployment but don't actually deploy.",
    ),
    api_url: Optional[str] = typer.Option(
        None,
        "--api-url",
        help="Secrets API URL. Overrides MCP_SECRETS_API_URL environment variable.",
    ),
    api_token: Optional[str] = typer.Option(
        None,
        "--api-token",
        help="Secrets API token. Overrides MCP_API_TOKEN environment variable.",
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
        api_url: Secrets API URL
        api_token: Secrets API token
        
    Returns:
        Path to the main configuration file
    """
    # Display deployment info
    print_info(f"Starting deployment with configuration: {config_file}")
    print_info(f"Using secrets file: {secrets_file}")
    print_info(f"Dry Run: {dry_run}")
    
    # Track the path to the configuration to use for deployment
    deployment_config_path = str(config_file)
    
    try:
        # Validate secrets-related environment variables or parameters
        if not no_secrets:
            effective_api_url = api_url or settings.SECRETS_API_URL
            effective_api_token = api_token or settings.SECRETS_API_TOKEN
            
            # Check for required Secrets API credentials - but only for real deployment
            if not dry_run:
                if not effective_api_url:
                    print_error("MCP_SECRETS_API_URL environment variable or --api-url option must be set.")
                    raise typer.Exit(1)
                if not effective_api_token:
                    print_error("MCP_API_TOKEN environment variable or --api-token option must be set.")
                    raise typer.Exit(1)
                print_info(f"Using Secrets API at {effective_api_url}")
            else:
                # For dry run, we'll use mock values if not provided
                effective_api_url = effective_api_url or "http://localhost:3000/api"
                effective_api_token = effective_api_token or "mock-token-for-dry-run"
                print_info(f"Using mock Secrets API at {effective_api_url} (dry run)")
        
        # Process secrets file
        if not no_secrets:
            # Process secrets file
            print_info("Processing secrets file...")
            secrets_transformed_path = secrets_output_file or f"{secrets_file}.transformed.yaml"
            
            if dry_run:
                # Use the mock client in dry run mode
                print_info("Using MOCK Secrets API client for dry run")
                
                # Create the mock client, capturing the return value to see the debug output
                mock_client = MockSecretsClient(
                    api_url=effective_api_url,
                    api_token=effective_api_token
                )
                
                # Process with the mock client, with more debug output
                print_info(f"Processing secrets file {secrets_file} with mock client")
                try:
                    _run_async(
                        process_config_secrets(
                            config_path=secrets_file,
                            output_path=secrets_transformed_path,
                            client=mock_client,
                            no_prompt=no_prompt
                        )
                    )
                    print_info("Secrets file processing completed successfully with mock client")
                except Exception as e:
                    print_error(f"Error during secrets processing with mock client: {str(e)}")
                    raise
            else:
                # Use the real API client
                _run_async(
                    process_config_secrets(
                        config_path=secrets_file,
                        output_path=secrets_transformed_path,
                        api_url=effective_api_url,
                        api_token=effective_api_token,
                        no_prompt=no_prompt
                    )
                )
            
            print_success("Secrets file processed successfully")
            print_info(f"Transformed secrets file written to {secrets_transformed_path}")
        else:
            print_info("Skipping secrets processing...")
        
        # Deploy agent
        if not dry_run:
            print_warning("TODO: Implement actual deployment logic")
            print_info("Deployment would happen here.")
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