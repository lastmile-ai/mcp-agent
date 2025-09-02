"""Processor for MCP Agent Cloud secrets.

This module provides functions for transforming configurations with secret tags
into deployment-ready configurations with secret handles.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import typer
import yaml

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
    SECRET_ID_PATTERN,
    SecretType,
)
from mcp_agent.cli.secrets.api_client import SecretsClient
from mcp_agent.cli.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    dump_yaml_with_secrets,
    load_yaml_with_secrets,
)
from mcp_agent.cli.utils.ux import (
    console,
    print_error,
    print_info,
    print_secret_prompt,
    print_secret_summary,
    print_warning,
)


async def process_config_secrets(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    client: Optional[SecretsClient] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    non_interactive: bool = False,
) -> Dict[str, Any]:
    """Process secrets in a configuration file.

    This function:
    1. Loads a YAML configuration file with custom tag handlers
    2. Loads existing transformed configuration if output_path exists
    3. Transforms the configuration recursively, replacing developer secrets with UUID handles
       - Reuses existing transformed secrets from output_path where possible
       - Transforms new developer secrets not found in output_path
       - Removes old transformed secrets that are no longer in the input
    4. Writes the transformed configuration to an output file

    Args:
        input_path: Path to the input configuration file
        output_path: Path to write the transformed configuration
        client: SecretsClient instance (optional, will create one if not provided)
        api_url: API URL for creating a new client (ignored if client is provided)
        api_key: API key for creating a new client (ignored if client is provided)
        non_interactive: Never prompt for missing values (fail instead)

    Returns:
        Dict with statistics about processed secrets
    """
    # Convert path arguments to strings if they're Path objects
    if isinstance(input_path, Path):
        input_path = str(input_path)

    if isinstance(output_path, Path):
        output_path = str(output_path)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            input_secrets_content = f.read()
    except Exception as e:
        print_error(f"Failed to read secrets file: {str(e)}")
        raise

    # Create client if not provided
    if client is None:
        effective_api_url = api_url or settings.API_BASE_URL
        effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

        if not effective_api_key:
            print_warning("No API key provided. Using empty key.")
            effective_api_key = ""

        # Create a new client
        client = SecretsClient(api_url=effective_api_url, api_key=effective_api_key)

    # Load existing transformed config if available to reuse processed secrets
    existing_secrets_content = None
    if output_path and os.path.exists(output_path):
        print_info(
            f"Found existing transformed secrets to use where applicable: {output_path}"
        )
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_secrets_content = f.read()
        except Exception as e:
            print_warning(f"Failed to load existing secrets for reuse: {str(e)}")

    # Process the content
    try:
        transformed_config = await process_secrets_in_config_str(
            input_secrets_content=input_secrets_content,
            existing_secrets_content=existing_secrets_content,
            client=client,
            non_interactive=non_interactive,
        )

        processed_content = dump_yaml_with_secrets(transformed_config)
    except Exception as e:
        print_error(f"Failed to process secrets: {str(e)}")
        raise

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(processed_content)
            print_info(f"Transformed config written to {output_path}")
        except Exception as e:
            print_error(f"Failed to write output file: {str(e)}")
            raise

    # Get the secrets context from the client if available
    if hasattr(client, "secrets_context"):
        secrets_context = client.secrets_context
    else:
        # Create a basic context if not available from the client
        secrets_context = {
            "developer_secrets": [],
            "user_secrets": [],
            "env_loaded": [],
            "prompted": [],
            "reused_secrets": [],
        }

    # Show a summary of the processed secrets
    print_secret_summary(secrets_context)

    return secrets_context


async def process_secrets_in_config_str(
    input_secrets_content: str,
    existing_secrets_content: Optional[str],
    client: SecretsClient,
    non_interactive: bool = False,
) -> Any:
    """Process secrets in a configuration string.

    This function:
    1. Parses a YAML string with custom tag handlers
    2. If existing_secrets_content is provided, parses it to reuse secrets
    3. Transforms the parsed object recursively, reusing existing secrets where possible
    4. Returns the transformed object (not a string)

    Args:
        input_secrets_content: YAML string with secret tags
        existing_secrets_content: Optional YAML string with existing transformed secrets
        client: SecretsClient instance for creating secrets
        non_interactive: Never prompt for missing values (fail instead)

    Returns:
        Transformed configuration object with developer secrets replaced by handles
    """
    # Initialize secrets context for tracking statistics
    secrets_context: Dict[str, Sequence] = {
        "developer_secrets": [],
        "user_secrets": [],
        "env_loaded": [],
        "prompted": [],
        "reused_secrets": [],
    }

    # Make the context available to the client for later retrieval
    setattr(client, "secrets_context", secrets_context)

    # Parse the input YAML with custom tag handling
    try:
        input_config = load_yaml_with_secrets(input_secrets_content)
    except Exception as e:
        print_error(f"Failed to parse input YAML: {str(e)}")
        raise

    # Parse the existing secrets YAML if provided
    existing_config = None
    if existing_secrets_content:
        try:
            existing_config = load_yaml_with_secrets(existing_secrets_content)
            print_info("Loaded existing secrets configuration for reuse")
        except Exception as e:
            print_warning(f"Failed to parse existing secrets YAML: {str(e)}")
            existing_config = None

    # Make sure the existing config secrets are actually valid for the user
    if existing_config:
        await validate_config_secrets(existing_config, client)

    # Transform the config recursively, passing existing config for reuse
    transformed_config = await transform_config_recursive(
        input_config,
        client,
        "",  # Start with empty path
        non_interactive,
        secrets_context,
        existing_config,
    )

    return transformed_config


async def validate_config_secrets(config: Dict[str, Any], client: SecretsClient):
    """Validate the secrets in the configuration against the SecretsClient with current API key
    to ensure they can be resolved.
    """
    for value in config.values():
        if isinstance(value, str) and SECRET_ID_PATTERN.match(value):
            # Check if the secret can be accessed
            try:
                if not await client.get_secret_value(value):
                    raise ValueError(f"Unable to resolve secret: {value}")
            except Exception as e:
                raise ValueError(f"Error resolving secret '{value}': {str(e)}")
        elif isinstance(value, dict):
            # Recursively validate nested dictionaries
            await validate_config_secrets(value, client)


async def transform_config_recursive(
    config: Any,
    client: SecretsClient,
    path: str = "",
    non_interactive: bool = False,
    secrets_context: Optional[Dict[str, Any]] = None,
    existing_config: Optional[Dict[str, Any]] = None,
) -> Any:
    """Recursively transform a config dictionary, replacing developer secrets with handles.

    For deploy-phase, only developer secrets are processed and replaced with secret handles.
    User secrets are left as-is to be processed during the configure phase.

    If existing_config is provided, the function will attempt to reuse existing secret handles
    for developer secrets that are already transformed in the existing configuration.

    Args:
        config: The configuration dictionary/value to transform
        client: The secrets client
        path: The current path in the config (for naming secrets)
        non_interactive: Never prompt for missing values (fail instead)
        secrets_context: Dictionary to track secret processing information
        existing_config: Optional existing transformed configuration to reuse secret handles from

    Returns:
        The transformed configuration
    """
    # Initialize context if not provided
    if secrets_context is None:
        secrets_context = {
            "developer_secrets": [],
            "user_secrets": [],
            "env_loaded": [],
            "prompted": [],
            "reused_secrets": [],
        }

    # For debugging, check if the config is a string with a tag prefix
    if isinstance(config, str) and (
        config.startswith("!developer_secret") or config.startswith("!user_secret")
    ):
        print_warning(f"Found raw string with tag prefix at path '{path}': {config}")
        # This indicates a YAML parsing issue - tags should be objects, not strings

    # Helper function to get value at a specific path in the existing config
    def get_at_path(config_dict, path_str):
        if not config_dict or not path_str:
            return None

        parts = path_str.split(".")
        curr = config_dict

        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                # Handle array indices in path like "path[0]"
                if "[" in part and "]" in part:
                    base_part = part.split("[")[0]
                    idx_str = part.split("[")[1].split("]")[0]
                    try:
                        idx = int(idx_str)
                        if (
                            base_part in curr
                            and isinstance(curr[base_part], list)
                            and idx < len(curr[base_part])
                        ):
                            curr = curr[base_part][idx]
                        else:
                            return None
                    except (ValueError, IndexError):
                        return None
                else:
                    return None

        return curr

    if isinstance(config, DeveloperSecret):
        # Check if this developer secret already exists in the transformed config
        existing_handle = None
        if existing_config is not None:
            existing_handle = get_at_path(existing_config, path)

            # Verify that the existing handle looks like a valid secret handle
            if isinstance(existing_handle, str) and SECRET_ID_PATTERN.match(
                existing_handle
            ):
                # Reuse the existing handle instead of creating a new secret
                print_info(
                    f"Reusing existing developer secret handle at '{path}': {existing_handle}"
                )

                # Add to the secrets context
                if "reused_secrets" not in secrets_context:
                    secrets_context["reused_secrets"] = []

                secrets_context["reused_secrets"].append(
                    {
                        "path": path,
                        "handle": existing_handle,
                    }
                )

                return existing_handle

        # Process developer secret - create a new one if no existing handle found
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
                    print_secret_prompt(env_var, path)
                    env_value = typer.prompt(
                        f"Enter value for {env_var}",
                        hide_input=True,
                        default="",
                        show_default=False,
                    )
                    was_prompted = True
                    secrets_context["prompted"].append(path)
                    if not env_value:
                        print_warning(f"No value provided for {env_var}.")
            else:
                # Value was found in environment
                from_env = True
                secrets_context["env_loaded"].append(path)
                print_info(
                    f"Loaded secret value for {path} from environment variable {env_var}"
                )

            value = env_value

        # Create the secret in the backend
        try:
            # Record that we're creating this secret (only log to file)
            print_info(
                f"Creating developer secret at {path}...",
                log=True,
                console_output=False,
            )
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
                            print_warning(
                                f"Attempt {attempt}/{max_attempts}: Developer secret at {path} still has no value."
                            )
                        else:
                            print_warning(
                                f"Developer secret at {path} has no value. Developer secrets must have values."
                            )

                        # Give the user a chance to provide a value
                        value = typer.prompt(
                            f"Enter value for developer secret at {path}",
                            hide_input=True,
                            default="",
                            show_default=False,
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
                value=value or "",  # Ensure value is never None
            )

            # Announce successful creation to console
            print_info(f"Secret created at '{path}' with handle: {handle}")

            # Add to the secrets context
            secrets_context["developer_secrets"].append(
                {
                    "path": path,
                    "handle": handle,
                    "from_env": from_env,
                    "was_prompted": was_prompted,
                }
            )

            return handle

        except Exception as e:
            print_error(f"Failed to create developer secret at {path}: {str(e)}")
            raise

    elif isinstance(config, UserSecret):
        # For deploy phase, keep user secrets as-is
        # They will be processed during the configure phase
        print_info(
            f"Keeping user secret at {path} as-is for configure phase",
            console_output=False,
        )
        if path not in secrets_context["user_secrets"]:
            secrets_context["user_secrets"].append(path)
        return config

    elif isinstance(config, dict):
        # Process each key in the dictionary
        result = {}
        for key, value in config.items():
            new_path = f"{path}.{key}" if path else key
            result[key] = await transform_config_recursive(
                value,
                client,
                new_path,
                non_interactive,
                secrets_context,
                existing_config,
            )
        return result

    elif isinstance(config, list):
        # Process each item in the list
        result_list = []
        for i, value in enumerate(config):
            new_path = f"{path}[{i}]" if path else f"[{i}]"
            result_list.append(
                await transform_config_recursive(
                    value,
                    client,
                    new_path,
                    non_interactive,
                    secrets_context,
                    existing_config,
                )
            )
        return result_list

    else:
        # We only want to support explicit developer and user secrets tags. Raw string values should not be processed.
        # However, allow $schema since that defines the structure of the config.
        if path == "$schema":
            return config

        raise ValueError(
            f"Unsupported value at path '{path}'. Secrets must be tagged with !developer_secret or !user_secret."
        )


async def configure_user_secrets(
    required_secrets: List[str],
    config_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    client: Optional[SecretsClient] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Configure required user secrets using a configuration file or interactive prompting.

    Args:
        required_secrets: List of required user secret keys to configure
        config_path: Path to a YAML secrets file containing processed user secret IDs
        output_path: Path to write processed secrets YAML from interactive prompting
        client: SecretsClient instance (optional, will create one if not provided)
        api_url: API URL for creating a new client (ignored if client is provided)
        api_key: API key for creating a new client (ignored if client is provided)

    Returns:
        Dict with secret keys and processed secret IDs
    """
    if len(required_secrets) == 0:
        return {}

    # Convert path arguments to strings if they're Path objects
    if config_path is not None and isinstance(config_path, Path):
        config_path = str(config_path)

    if output_path is not None and isinstance(output_path, Path):
        output_path = str(output_path)

    if config_path and output_path:
        raise ValueError(
            "Cannot specify both config_path and output_path. Use one or the other."
        )

    # If config path is provided, just grab all required secrets from it
    if config_path:
        return retrieve_secrets_from_config(config_path, required_secrets)
    elif not output_path:
        raise ValueError(
            "Must provide either config_path or output_path to configure user secrets."
        )

    # Create client if not provided
    if client is None:
        # Get API URL and key from parameters or environment variables
        effective_api_url: str = (
            api_url
            or os.environ.get(ENV_API_BASE_URL, DEFAULT_API_BASE_URL)
            or DEFAULT_API_BASE_URL
        )
        effective_api_key = api_key or os.environ.get(ENV_API_KEY, "")

        if not effective_api_key:
            print_warning("No API key provided. Using empty key.")
            effective_api_key = ""

        # Create a new client
        client = SecretsClient(api_url=effective_api_url, api_key=effective_api_key)

    processed_secrets = await process_prompted_user_secrets(required_secrets, client)

    # Write the output file if specified
    if output_path:
        try:
            nested_secrets = nest_keys(processed_secrets)
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    nested_secrets,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print_info(f"Processed secret IDs written to {output_path}")
        except Exception as e:
            print_error(f"Failed to write output file: {str(e)}")
            raise

    return processed_secrets


def nest_keys(flat_dict: dict[str, str]) -> dict:
    """Convert flat dict with dot-notation keys to nested dict."""
    nested: Dict[str, Any] = {}
    for flat_key, value in flat_dict.items():
        parts = flat_key.split(".")
        d = nested
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return nested


def get_nested_key_value(config: dict, dotted_key: str) -> Any:
    parts = dotted_key.split(".")
    value = config
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"Required secret '{dotted_key}' not found in config.")
        value = value[part]
    return value


def retrieve_secrets_from_config(
    config_path: str, required_secrets: List[str]
) -> Dict[str, str]:
    """Retrieve dot-notated user secrets from a YAML configuration file.

    This function reads a YAML configuration file and extracts user secrets
    based on the provided required secret keys.

    Args:
        config_path: Path to the configuration file
        required_secrets: List of required user secret keys to retrieve

    Returns:
        Dict with secret keys and their corresponding values
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = load_yaml_with_secrets(f.read())
    except Exception as e:
        print_error(f"Failed to read or parse config file: {str(e)}")
        raise

    secrets = {}

    for secret_key in required_secrets:
        value = get_nested_key_value(config, secret_key)
        if not SECRET_ID_PATTERN.match(value):
            raise ValueError(
                f"Secret '{secret_key}' in config does not match expected secret ID pattern"
            )
        secrets[secret_key] = value

    return secrets


MAX_PROMPT_RETRIES = 3


async def process_prompted_user_secrets(
    required_secrets: List[str], client: SecretsClient
) -> Dict[str, str]:
    """Process user secrets by prompting for their values with retries and a Rich spinner."""
    processed_secrets = {}

    for secret_key in required_secrets:
        for attempt in range(1, MAX_PROMPT_RETRIES + 1):
            try:
                secret_value = typer.prompt(
                    f"Enter value for user secret '{secret_key}'",
                    hide_input=True,
                    default="",
                    show_default=False,
                )

                if not secret_value or secret_value.strip() == "":
                    raise ValueError(
                        f"User secret '{secret_key}' requires a non-empty value"
                    )

                if SECRET_ID_PATTERN.match(secret_value):
                    raise ValueError(
                        f"User secret '{secret_key}' must have raw value set, not secret ID"
                    )

                with console.status(f"[bold green]Creating secret '{secret_key}'..."):
                    secret_id = await client.create_secret(
                        name=secret_key,
                        secret_type=SecretType.USER,
                        value=secret_value,
                    )

                processed_secrets[secret_key] = secret_id
                console.print(
                    f"[green]✓[/green] User secret '{secret_key}' created with ID: [bold]{secret_id}[/bold]"
                )
                break  # Success, move to next secret

            except Exception as e:
                console.print(
                    f"[red]✗[/red] [Attempt {attempt}/{MAX_PROMPT_RETRIES}] Failed to set secret '{secret_key}': {e}"
                )
                if attempt == MAX_PROMPT_RETRIES:
                    raise RuntimeError(
                        f"Giving up on secret '{secret_key}' after {MAX_PROMPT_RETRIES} attempts."
                    ) from e

    return processed_secrets
