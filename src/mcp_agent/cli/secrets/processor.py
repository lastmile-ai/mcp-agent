"""Processor for MCP Agent Cloud secrets.

This module provides functions for transforming configurations with secret tags
into deployment-ready configurations with secret handles.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import typer
import yaml
from rich.prompt import Prompt

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
    SECRET_ID_PATTERN,
    SecretType,
)
from mcp_agent.cli.exceptions import CLIError
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
    1. Loads a YAML secrets file from input_path
    2. Loads existing transformed secrets file from output_path if it exists
    3. Transforms the input secrets recursively:
        - If non-interactive is True, automatically transforms all secrets to
            developer secrets without prompting, reusing existing secrets where applicable
        - Otherwise:
            - Prompts to determine whether a secret is a developer secret to transform
                or a user secret to tag as !user_secret for subsequent configured deployments
            - Prompts to handle existing secrets that appear in both output and input files
            - Prompts to remove old transformed secrets that are no longer in the input
    4. Writes the transformed secrets configuration to the output file

    Args:
        input_path: Path to the input secrets file
        output_path: Path to write the transformed secrets configuration
        client: SecretsClient instance (optional, will create one if not provided)
        api_url: API URL for creating a new client (ignored if client is provided)
        api_key: API key for creating a new client (ignored if client is provided)
        non_interactive: Never prompt for transformation decisions, follow specification above

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
            raise CLIError(
                "Must have API key to process secrets. Login via 'mcp-agent login'.",
                retriable=False,
            )

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
            raise CLIError(
                f"Failed to load existing secrets for reuse: {str(e)}"
            ) from e

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
        raise CLIError(f"Failed to process secrets: {str(e)}") from e

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(processed_content)
            print_info(f"Transformed config written to {output_path}")
        except Exception as e:
            raise CLIError(f"Failed to write output file: {str(e)}") from e

    # Get the secrets context from the client if available
    if hasattr(client, "secrets_context"):
        secrets_context = client.secrets_context
    else:
        # Create a basic context if not available from the client
        secrets_context = {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
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
    1. Parses an input YAML string with raw secrets
    2. If existing_secrets_content is provided, parses it to possibly reuse secrets (prompting if needed)
    3. Transforms the parsed object recursively
    4. Returns the transformed object (not a string)

    Args:
        input_secrets_content: YAML string with raw secrets
        existing_secrets_content: Optional YAML string with existing transformed secrets and tags
        client: SecretsClient instance for creating secrets
        non_interactive: Never prompt for transformation decisions, reuse existing secrets where applicable

    Returns:
        Transformed configuration object with raw secrets replaced by secret handles and user secrets replaced
        by !user_secret tags
    """
    # Initialize secrets context for tracking statistics
    secrets_context: Dict[str, Sequence] = {
        "deployment_secrets": [],
        "user_secrets": [],
        "reused_secrets": [],
        "skipped_secrets": [],
    }

    # Make the context available to the client for later retrieval
    setattr(client, "secrets_context", secrets_context)

    # Parse the input secrets YAML (should not have custom tags)
    try:
        input_config = yaml.safe_load(input_secrets_content)
    except Exception as e:
        raise CLIError(f"Failed to parse input YAML: {str(e)}", retriable=False) from e

    # Parse the existing secrets YAML if provided
    existing_config = None
    if existing_secrets_content:
        try:
            existing_config = load_yaml_with_secrets(existing_secrets_content)
            print_info("Loaded existing secrets configuration for reuse")
        except Exception as e:
            raise CLIError(
                f"Failed to parse existing secrets YAML: {str(e)}", retriable=False
            ) from e

    # Make sure the existing config secrets are actually valid for the user
    if existing_config:
        existing_config = await get_validated_config_secrets(
            input_config, existing_config, client, non_interactive, ""
        )

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


async def get_validated_config_secrets(
    input_config: Dict[str, Any],
    existing_config: Dict[str, Any],
    client: SecretsClient,
    non_interactive: bool,
    path: str = "",
) -> Dict[str, Any]:
    """Validate the secrets in the existing_config against the SecretsClient with current API key
    to ensure they can be resolved. Return a subset of existing_config containing only keys/values
    that exist in input_config and match the input values, without reprocessing them.

    Args:
        input_config: The new input configuration (should contain raw secrets, not tags)
        existing_config: The existing transformed configuration
        client: SecretsClient for validating secret handles
        non_interactive: Whether to skip interactive prompts

    Returns:
        A subset of existing_config with keys/values that are good to keep as-is
    """
    validated_config = {}

    for key, existing_value in existing_config.items():
        current_path = f"{path}.{key}" if path else key

        if isinstance(existing_value, str) and SECRET_ID_PATTERN.match(existing_value):
            if key not in input_config:
                if not non_interactive:
                    should_exclude = typer.confirm(
                        f"Secret at '{current_path}' exists in existing transformed secrets file but not in raw secrets file. Exclude it?",
                        default=True,
                    )
                    if should_exclude:
                        continue
                else:
                    continue
            else:
                # Validate input config value is raw (not tagged)
                input_value = input_config[key]
                if isinstance(input_value, (DeveloperSecret, UserSecret)):
                    raise ValueError(
                        f"Input secrets config at '{current_path}' contains secret tag. Input should contain raw secrets, not tags."
                    )

            # Validate the secret can be resolved and then validate it against existing input value
            try:
                secret_value = await client.get_secret_value(existing_value)
                if not secret_value:
                    raise ValueError(
                        f"Transformed secret handle '{existing_value}' at '{current_path}' could not be resolved."
                    )

                if key in input_config:
                    if input_config[key] == secret_value:
                        validated_config[key] = existing_value
                    else:
                        if non_interactive:
                            print_warning(
                                f"Secret at '{current_path}' value in transformed secrets file does not match raw secrets file. It will be reprocessed."
                            )
                        else:
                            reprocess = typer.confirm(
                                f"Secret at '{current_path}' value in transformed secrets file does not match raw secrets file. Do you want to reprocess it?",
                                default=True,
                            )
                            if reprocess:
                                continue
                            else:
                                validated_config[key] = existing_value

            except Exception as e:
                raise CLIError(
                    f"Failed to validate secret at '{current_path}' in transformed secrets file: {str(e)}"
                ) from e

        elif isinstance(existing_value, DeveloperSecret):
            raise ValueError(
                f"Found unexpected !developer_secret tag in existing transformed config at '{current_path}'. Existing config should only contain secret handles or !user_secret tags."
            )

        elif isinstance(existing_value, dict):
            # Always recursively process nested dictionaries
            input_dict = (
                input_config.get(key, {})
                if isinstance(input_config.get(key), dict)
                else {}
            )
            nested_validated = await get_validated_config_secrets(
                input_dict, existing_value, client, non_interactive, current_path
            )

            if nested_validated:
                validated_config[key] = nested_validated

    return validated_config


async def transform_config_recursive(
    config_value: Any,
    client: SecretsClient,
    path: str = "",
    non_interactive: bool = False,
    secrets_context: Optional[Dict[str, Any]] = None,
    existing_config: Optional[Dict[str, Any]] = None,
) -> Any:
    """Recursively transform a config dictionary, replacing raw secrets with handles or !user_secret tags.

    If existing_config is provided, the function will reuse existing secret handles that are already transformed
    in the existing configuration. The remaining raw secrets in the input config will be transformed to handles
    or !user_secret tags based on user prompts (unless non_interactive is True, in which case the raw secrets will
    be transformed to secret handles without prompting).

    Args:
        config_value: The input (raw secrets) configuration dictionary/value to transform. Recursively passed config value.
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
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    if isinstance(config_value, (DeveloperSecret, UserSecret)):
        raise ValueError(
            f"\nInput secrets config at path '{path}' contains secret tag. Input should contain raw secrets, not tags."
        )

    elif isinstance(config_value, dict):
        # Process each key in the dictionary
        result = {}
        for key, value in config_value.items():
            new_path = f"{path}.{key}" if path else key
            try:
                transformed_value = await transform_config_recursive(
                    value,
                    client,
                    new_path,
                    non_interactive,
                    secrets_context,
                    existing_config,
                )
                if transformed_value:
                    result[key] = transformed_value
            except Exception as e:
                print_error(
                    f"\nError processing secret at '{new_path}': {str(e)}\n Skipping this secret."
                )
                if "skipped_secrets" not in secrets_context:
                    secrets_context["skipped_secrets"] = []
                secrets_context["skipped_secrets"].append(new_path)
                # Just skip this key since raising would abort all valid processing
                continue
        return result

    elif isinstance(config_value, list):
        # Process each item in the list
        result_list = []
        for i, value in enumerate(config_value):
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

    elif isinstance(config_value, str):
        # Skip processing $schema key since we know it's not a secret
        if path == "$schema":
            return config_value

        if config_value.startswith("!developer_secret") or config_value.startswith(
            "!user_secret"
        ):
            # This indicates a YAML parsing issue - tags should be objects, not strings
            raise ValueError(
                f"\nFound raw string with tag prefix at path '{path}' in secrets file"
            )

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

        # Reuse existing secret if available
        existing_handle = None
        if existing_config is not None:
            existing_handle = get_at_path(existing_config, path)

            # Verify that the existing handle looks like a valid secret handle
            if isinstance(existing_handle, str) and SECRET_ID_PATTERN.match(
                existing_handle
            ):
                print_info(
                    f"\nReusing existing deployment secret handle at '{path}': {existing_handle}"
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

        # Check if it's a deployment secret or a user secret
        if not non_interactive:
            choices = {
                "1": "Deployment Secret: The secret value will be stored securely and accessible to the deployed application runtime.",
                "2": "User Secret: No secret value will be stored. The 'configure' command must be used to create a configured application with this secret.",
            }

            # Print the numbered options
            console.print(f"\n[bold]Select secret type for '{path}'[/bold]")
            for key, description in choices.items():
                console.print(f"[cyan]{key}[/cyan]: {description}")

            choice = Prompt.ask(
                "\nSelect secret type:",
                choices=list(choices.keys()),
                default="1",
                show_choices=False,
            )

            if choice == "2":
                print_info(f"Tagging '{path}' as a user secret (!user_secret)")
                if "user_secrets" not in secrets_context:
                    secrets_context["user_secrets"] = []
                secrets_context["user_secrets"].append(path)
                return UserSecret()

        # Create a transformed deployment secret
        try:
            print_info(
                f"\nCreating deployment secret at {path}...",
                log=True,
                console_output=False,
            )
            if config_value is None or config_value == "":
                raise ValueError(
                    f"\nSecret at {path} has no value. Deployment secrets must have values."
                )

            # Create the secret in the backend, getting a handle in return
            handle = await client.create_secret(
                name=path or "unknown.path",
                secret_type=SecretType.DEVELOPER,
                value=config_value,
            )

            print_info(f"Secret created at '{path}' with handle: {handle}")
            secrets_context["deployment_secrets"].append(
                {
                    "path": path,
                    "handle": handle,
                }
            )

            return handle

        except Exception as e:
            raise CLIError(
                f"\nFailed to create deployment secret handle for {path}: {str(e)}"
            ) from e


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
