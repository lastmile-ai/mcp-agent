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
from ..secrets.constants import SecretsMode
from ..secrets.processor import process_config_secrets
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
    secrets_mode: Optional[str] = typer.Option(
        None,
        "--secrets-mode",
        help="Mode for handling secrets in configuration files (direct_vault or api).",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        "-o",
        help="Path to write the transformed configuration file.",
        resolve_path=True,
    ),
    no_secrets: bool = typer.Option(
        False,
        "--no-secrets",
        help="Skip secrets processing.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate the deployment but don't actually deploy.",
    ),
    vault_addr: Optional[str] = typer.Option(
        None,
        "--vault-addr",
        help="Vault server address. Overrides VAULT_ADDR environment variable.",
    ),
    vault_token: Optional[str] = typer.Option(
        None,
        "--vault-token",
        help="Vault token. Overrides VAULT_TOKEN environment variable.",
    ),
    api_url: Optional[str] = typer.Option(
        None,
        "--api-url",
        help="Secrets API URL. Overrides MCP_SECRETS_API_URL environment variable.",
    ),
    api_token: Optional[str] = typer.Option(
        None,
        "--api-token",
        help="Secrets API token. Overrides MCP_SECRETS_API_TOKEN environment variable.",
    ),
) -> str:
    """Deploy an MCP agent using the specified configuration.
    
    This function:
    1. Processes the configuration file, transforming secret tags to handles
    2. Deploys the agent with the transformed configuration
    
    Args:
        config_file: Path to the configuration file
        secrets_mode: The secrets handling mode (direct_vault or api)
        output_file: Path to write the transformed configuration file
        no_secrets: Skip secrets processing
        dry_run: Validate the deployment but don't actually deploy
        vault_addr: Vault server address
        vault_token: Vault token
        api_url: Secrets API URL
        api_token: Secrets API token
        
    Returns:
        Path to the processed configuration file
    """
    # Get effective secrets mode from param or env var
    effective_secrets_mode = (
        secrets_mode 
        or settings.SECRETS_MODE  # Use uppercase for backward compatibility
    )
    
    # Display deployment info
    print_info(f"Starting deployment with configuration: {config_file}")
    print_info(f"Secrets Mode: {effective_secrets_mode}")
    print_info(f"Dry Run: {dry_run}")
    
    # Track the path to the configuration to use for deployment
    deployment_config_path = str(config_file)
    
    try:
        # Validate secrets-related environment variables or parameters
        if not no_secrets:
            effective_vault_addr = vault_addr or settings.VAULT_ADDR
            effective_vault_token = vault_token or settings.VAULT_TOKEN
            effective_api_url = api_url or settings.SECRETS_API_URL
            effective_api_token = api_token or settings.SECRETS_API_TOKEN
            
            if effective_secrets_mode == SecretsMode.DIRECT_VAULT:
                # Check for required Vault credentials
                if not effective_vault_addr:
                    print_error("VAULT_ADDR environment variable or --vault-addr option must be set.")
                    raise typer.Exit(1)
                if not effective_vault_token:
                    print_error("VAULT_TOKEN environment variable or --vault-token option must be set.")
                    raise typer.Exit(1)
                
                print_info(f"Using Vault at {effective_vault_addr}")
            elif effective_secrets_mode == SecretsMode.API:
                # Check for required Secrets API credentials
                if not effective_api_url:
                    print_error("MCP_SECRETS_API_URL environment variable or --api-url option must be set.")
                    raise typer.Exit(1)
                if not effective_api_token:
                    print_error("MCP_SECRETS_API_TOKEN environment variable or --api-token option must be set.")
                    raise typer.Exit(1)
                
                print_info(f"Using Secrets API at {effective_api_url}")
        
        # Process configuration
        if not no_secrets:
            print_info("Processing secrets in configuration...")
            transformed_config_path = output_file or f"{config_file}.transformed.yaml"
            
            # Use the helper to properly handle event loops in all contexts
            _run_async(
                process_config_secrets(
                    config_path=config_file,
                    output_path=transformed_config_path,
                    secrets_mode=effective_secrets_mode,
                    vault_addr=effective_vault_addr,
                    vault_token=effective_vault_token,
                    api_url=effective_api_url,
                    api_token=effective_api_token,
                )
            )
            
            print_success(f"Secrets processed successfully")
            print_info(f"Transformed configuration written to {transformed_config_path}")
            
            # Use the transformed config for deployment
            deployment_config_path = str(transformed_config_path)
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