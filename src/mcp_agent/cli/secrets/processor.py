"""Processor for MCP Agent Cloud secrets.

This module provides functions for transforming configurations with secret tags
into deployment-ready configurations with secret handles.
"""

import os
import re
from typing import Any, Dict, Optional, Union
from pathlib import Path

import typer
import yaml

from ..core.constants import SecretType, UUID_PREFIX
from .yaml_tags import DeveloperSecret, UserSecret, load_yaml_with_secrets, dump_yaml_with_secrets
from .api_client import SecretsClient
from ..ux import print_info, print_warning, print_error, print_success, print_secret_summary


async def process_config_secrets(
    config_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    client: Optional[SecretsClient] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    non_interactive: bool = False,
) -> Dict[str, Any]:
    """Process secrets in a configuration file.
    
    This function:
    1. Loads a YAML configuration file with custom tag handlers
    2. Transforms the configuration recursively, replacing developer secrets with UUID handles
    3. Writes the transformed configuration to an output file
    
    Args:
        config_path: Path to the input configuration file
        output_path: Path to write the transformed configuration
        client: SecretsClient instance (optional, will create one if not provided)
        api_url: API URL for creating a new client (ignored if client is provided)
        api_key: API key for creating a new client (ignored if client is provided)
        non_interactive: Never prompt for missing values (fail instead)
        
    Returns:
        Dict with statistics about processed secrets
    """
    # Convert path to string if it's a Path object
    if isinstance(config_path, Path):
        config_path = str(config_path)
    
    if output_path is not None and isinstance(output_path, Path):
        output_path = str(output_path)
    
    # Read the config file
    try:
        with open(config_path, 'r') as f:
            config_content = f.read()
    except Exception as e:
        print_error(f"Failed to read config file: {str(e)}")
        raise
    
    # Create client if not provided
    if client is None:
        from .api_client import create_secrets_client
        client = await create_secrets_client(api_url, api_key)
    
    # Process the content
    try:
        processed_content = await process_secrets_in_config(
            config_content, 
            client,
            non_interactive=non_interactive
        )
    except Exception as e:
        print_error(f"Failed to process secrets: {str(e)}")
        raise
    
    # Write the output file if specified
    if output_path:
        try:
            with open(output_path, 'w') as f:
                f.write(processed_content)
            print_info(f"Transformed config written to {output_path}")
        except Exception as e:
            print_error(f"Failed to write output file: {str(e)}")
            raise
            
    # Get the context object from the last run
    if hasattr(client, 'secrets_context'):
        secrets_context = client.secrets_context
    else:
        # Create a basic context if not available from the client
        secrets_context = {
            'developer_secrets': [],
            'user_secrets': [],
            'env_loaded': [],
            'prompted': []
        }
    
    # Show a summary of the processed secrets
    print_secret_summary(secrets_context)
    
    return secrets_context


async def process_secrets_in_config(
    config_content: str,
    client: SecretsClient,
    non_interactive: bool = False,
) -> str:
    """Process secrets in a configuration string.
    
    This function:
    1. Parses a YAML string with custom tag handlers
    2. Transforms the parsed object recursively
    3. Returns the transformed object as a YAML string
    
    Args:
        config_content: YAML string with secret tags
        client: SecretsClient instance for creating secrets
        non_interactive: Never prompt for missing values (fail instead)
        
    Returns:
        Transformed YAML string with developer secrets replaced by handles
    """
    # Initialize secrets context for tracking
    secrets_context = {
        'developer_secrets': [],
        'user_secrets': [],
        'env_loaded': [],
        'prompted': []
    }
    
    # Parse the YAML with custom tag handling
    try:
        config = load_yaml_with_secrets(config_content)
    except Exception as e:
        print_error(f"Failed to parse YAML: {str(e)}")
        raise
    
    # Store the context in the client for retrieval later
    if hasattr(client, 'secrets_context'):
        client.secrets_context = secrets_context
    
    # Transform the config recursively
    transformed_config = await transform_config_recursive(
        config,
        client,
        "",  # Start with empty path
        non_interactive,
        secrets_context
    )
    
    # Dump back to YAML string with proper formatting
    try:
        result_yaml = dump_yaml_with_secrets(transformed_config)
    except Exception as e:
        print_error(f"Failed to dump transformed YAML: {str(e)}")
        raise
    
    return result_yaml


async def transform_config_recursive(
    config: Any, 
    client: SecretsClient, 
    path: str = "",
    non_interactive: bool = False,
    secrets_context: Optional[Dict[str, Any]] = None
) -> Any:
    """Recursively transform a config dictionary, replacing developer secrets with handles.
    
    For deploy-phase, only developer secrets are processed and replaced with secret handles.
    User secrets are left as-is to be processed during the configure phase.
    
    Args:
        config: The configuration dictionary/value to transform
        client: The secrets client
        path: The current path in the config (for naming secrets)
        non_interactive: Never prompt for missing values (fail instead)
        secrets_context: Dictionary to track secret processing information
        
    Returns:
        The transformed configuration
    """
    # Initialize context if not provided
    if secrets_context is None:
        secrets_context = {
            'developer_secrets': [],
            'user_secrets': [],
            'env_loaded': [],
            'prompted': []
        }
    
    # For debugging, check if the config is a string with a tag prefix
    if isinstance(config, str) and (config.startswith('!developer_secret') or config.startswith('!user_secret')):
        print_warning(f"Found raw string with tag prefix at path '{path}': {config}")
        # This indicates a YAML parsing issue - tags should be objects, not strings
        
    if isinstance(config, DeveloperSecret):
        # Process developer secret - the meat of the transformation
        value = config.value
        from_env = False
        was_prompted = False
        env_var = None
        
        # Process environment variable references directly from the tag value
        # This is where environment variable resolution happens
        if isinstance(value, str):
            env_var = value  # The value is the environment variable name
            env_value = os.environ.get(env_var)
            if env_value is None:
                if non_interactive:
                    # Fail immediately when env var is missing and --non-interactive is set
                    error_msg = f"Developer secret at {path} has no value. Environment variable {env_var} not found and --non-interactive is set."
                    print_error(error_msg)
                    raise ValueError(error_msg)
                else:
                    # Prompt the user for the missing value
                    from ..ux import print_secret_prompt
                    print_secret_prompt(env_var, path)
                    env_value = typer.prompt(
                        f"Enter value for {env_var}",
                        hide_input=True,
                        default="",
                        show_default=False
                    )
                    was_prompted = True
                    secrets_context['prompted'].append(path)
                    if not env_value:
                        print_warning(f"No value provided for {env_var}.")
            else:
                # Value was found in environment
                from_env = True
                secrets_context['env_loaded'].append(path)
                print_info(f"Loaded secret value for {path} from environment variable {env_var}")
                
            value = env_value
            
        # Create the secret in the backend
        try:
            # Record that we're creating this secret (only log to file)
            print_info(f"Creating developer secret at {path}...", log=True, console_output=False)
            # Developer secrets must have values
            if value is None or value == "":
                if non_interactive:
                    # Don't prompt - just fail immediately
                    error_msg = f"Developer secret at {path} has no value. Developer secrets must have values. (--non-interactive is set)"
                    print_error(error_msg)
                    raise ValueError(error_msg)
                else:
                    # Prompt for a value with retries
                    max_attempts = 3
                    attempt = 1
                    
                    while (value is None or value == "") and attempt <= max_attempts:
                        if attempt > 1:
                            print_warning(f"Attempt {attempt}/{max_attempts}: Developer secret at {path} still has no value.")
                        else:
                            print_warning(f"Developer secret at {path} has no value. Developer secrets must have values.")
                        
                        # Give the user a chance to provide a value
                        value = typer.prompt(
                            f"Enter value for developer secret at {path}",
                            hide_input=True,
                            default="",
                            show_default=False
                        )
                        attempt += 1
                    
                    if value is None or value == "":
                        error_msg = f"Developer secret at {path} has no value after {max_attempts} attempts. Developer secrets must have values."
                        print_error(error_msg)
                        raise ValueError(error_msg)
            
            # Create the secret in the backend, getting a handle in return
            handle = await client.create_secret(
                name=path or "unknown.path",
                secret_type=SecretType.DEVELOPER,
                value=value or ""  # Ensure value is never None
            )
            
            # Announce successful creation to console
            print_info(f"Secret created at '{path}' with handle: {handle}")
            
            # Add to the secrets context
            secrets_context['developer_secrets'].append({
                'path': path,
                'handle': handle,
                'from_env': from_env,
                'was_prompted': was_prompted
            })
            
            return handle
            
        except Exception as e:
            print_error(f"Failed to create developer secret at {path}: {str(e)}")
            raise
        
    elif isinstance(config, UserSecret):
        # For deploy phase, keep user secrets as-is
        # They will be processed during the configure phase
        print_info(f"Keeping user secret at {path} as-is for configure phase", console_output=False)
        if path not in secrets_context['user_secrets']:
            secrets_context['user_secrets'].append(path)
        return config
        
    elif isinstance(config, dict):
        # Process each key in the dictionary
        result = {}
        for key, value in config.items():
            new_path = f"{path}.{key}" if path else key
            result[key] = await transform_config_recursive(value, client, new_path, non_interactive, secrets_context)
        return result
        
    elif isinstance(config, list):
        # Process each item in the list
        result = []
        for i, value in enumerate(config):
            new_path = f"{path}[{i}]" if path else f"[{i}]"
            result.append(await transform_config_recursive(value, client, new_path, non_interactive, secrets_context))
        return result
        
    else:
        # Return primitive values as-is
        return config