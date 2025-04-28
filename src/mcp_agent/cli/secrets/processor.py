"""Secret processing functionality for the MCP Agent Cloud.

This module handles the processing of user configuration files, including:
1. Detection of !developer_secret and !user_secret tags
2. Resolution of OmegaConf-style environment variables (${oc.env:VAR_NAME})
3. Integration with the Secrets API service
4. Transformation of configuration files for deployment

IMPORTANT NOTE ON CONFIGURATION SYSTEMS:
This module uses OmegaConf-style environment variable resolution in user YAML config files,
which is separate from the Pydantic Settings used for CLI configuration in settings.py.

Two separate configuration systems work together:
1. OmegaConf-style resolution (this module):
   - Processes environment variables in user configuration files using ${oc.env:VAR_NAME} syntax
   - Controls the actual values being stored as secrets

2. Pydantic Settings (settings.py):
   - Controls CLI behavior and connections to the Secrets API service
   - Determines how this processor behaves, not what values are processed

For example, when processing:
  api_key: !developer_secret ${oc.env:API_KEY}
  
1. This module resolves ${oc.env:API_KEY} to get the actual secret value
2. Then uses settings from settings.py to connect to the Secrets API
"""

import os
from typing import Any, Dict, Optional, Union
from pathlib import Path

import yaml
import typer

# Custom YAML tag handlers for secrets
class SecretBase(yaml.YAMLObject):
    """Base class for secret YAML tags."""
    
    def __init__(self, value: Optional[str] = None):
        self.value = value
    
    @classmethod
    def from_yaml(cls, loader, node):
        # Handle both scalar values and empty tags
        if isinstance(node, yaml.ScalarNode):
            return cls(loader.construct_scalar(node))
        return cls(None)
    
    def __repr__(self):
        return f"{self.__class__.__name__}(value={self.value})"


class DeveloperSecret(SecretBase):
    """Custom YAML tag for developer-provided secrets."""
    yaml_tag = u'!developer_secret'


class UserSecret(SecretBase):
    """Custom YAML tag for user-provided secrets."""
    yaml_tag = u'!user_secret'


# Create a custom YAML dumper to handle empty tags properly
class EmptyTagDumper(yaml.SafeDumper):
    """Custom YAML dumper that processes empty tags better."""
    
    def represent_scalar(self, tag, value, style=None):
        """Customize the representation of scalar values."""
        # For user_secret tags with empty strings, treat them specially
        if tag == '!user_secret' and (value is None or value == ''):
            # Use a null style (plain) for empty tags
            return yaml.ScalarNode(tag, '', style='')
        
        # For all other cases, use the default behavior
        return super().represent_scalar(tag, value, style=style)

# Register representation functions for our custom tag classes
def represent_user_secret(dumper, data):
    """Custom representation for UserSecret objects."""
    if data.value is None or data.value == '':
        # For empty values, use a tag with no content
        return dumper.represent_scalar('!user_secret', '')
    # For non-empty values, preserve them
    return dumper.represent_scalar('!user_secret', data.value)

def represent_developer_secret(dumper, data):
    """Custom representation for DeveloperSecret objects."""
    if data.value is None or data.value == '':
        # For empty values, use a tag with no content
        return dumper.represent_scalar('!developer_secret', '')
    # For non-empty values, preserve them
    return dumper.represent_scalar('!developer_secret', data.value)

# Register these representation functions with our dumper
EmptyTagDumper.add_representer(UserSecret, represent_user_secret)
EmptyTagDumper.add_representer(DeveloperSecret, represent_developer_secret)

from ..config import settings
from .constants import SecretType
from .api_client import SecretsClient
from ..ux import print_info, print_warning, print_error


async def process_config_secrets(
    config_path: Union[str, Path],
    output_path: Union[str, Path],
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    client: Optional[Any] = None,
    no_prompt: bool = False,
) -> None:
    """Process a configuration file, transforming secret tags to secret IDs.
    
    Args:
        config_path: Path to the configuration file
        output_path: Path to write the transformed configuration to
        api_url: Optional Secrets API URL, overrides environment variable
        api_token: Optional Secrets API token, overrides environment variable
        client: Optional pre-initialized secrets client (for testing or dry runs)
        no_prompt: Never prompt for missing values (fail instead)
    
    Raises:
        Exception: If processing fails
    """
    # Ensure paths are strings
    if isinstance(config_path, Path):
        config_path = str(config_path)
    if isinstance(output_path, Path):
        output_path = str(output_path)
    
    # Load the configuration file
    try:
        with open(config_path, 'r') as f:
            # Parse as string first to keep the tags
            config_str = f.read()
            # Also parse as YAML to work with the structure
            # Use yaml.load with our custom tag handlers
            config_yaml = yaml.load(config_str, Loader=yaml.FullLoader)
    except Exception as e:
        raise Exception(f"Error loading configuration file {config_path}: {e}")
    
    # Initialize the secrets client if not provided
    if client is None:
        client = SecretsClient(
            api_url=api_url or settings.SECRETS_API_URL,
            api_token=api_token or settings.SECRETS_API_TOKEN
        )
    
    # Process the configuration file for secrets
    transformed_str = await process_secrets_in_config(config_str, client, no_prompt)
    
    # Parse the transformed string back to YAML to validate
    try:
        transformed_yaml = yaml.load(transformed_str, Loader=yaml.FullLoader)
    except Exception as e:
        raise Exception(f"Error parsing transformed configuration: {e}")
    
    # Write the transformed configuration to the output file
    with open(output_path, 'w') as f:
        f.write(transformed_str)
    
    # Display the changes
    await compare_configs(config_yaml, transformed_yaml)


async def process_secrets_in_config(
    config_str: str, 
    client: SecretsClient,
    no_prompt: bool = False
) -> str:
    """Process secrets in the configuration string.
    
    Args:
        config_str: The configuration string containing secret tags
        client: The secrets client to use for creating secrets
        no_prompt: Never prompt for missing values (fail instead)
    
    Returns:
        The transformed configuration string with secret tags replaced by secret IDs
    """
    # Load the config with custom tag handlers
    config_yaml = yaml.load(config_str, Loader=yaml.FullLoader)
    
    # Process the loaded YAML recursively
    transformed_yaml = await transform_config_recursive(config_yaml, client, "", no_prompt)
    
    # Convert back to YAML string using our custom dumper
    transformed_str = yaml.dump(transformed_yaml, Dumper=EmptyTagDumper, default_flow_style=False)
    
    return transformed_str


async def transform_config_recursive(
    config: Any, 
    client: SecretsClient, 
    path: str = "",
    no_prompt: bool = False
) -> Any:
    """Recursively transform a config dictionary, replacing developer secrets with handles.
    
    For deploy-phase, only developer secrets are processed and replaced with secret handles.
    User secrets are left as-is to be processed during the configure phase.
    
    Args:
        config: The configuration dictionary/value to transform
        client: The secrets client
        path: The current path in the config (for naming secrets)
        no_prompt: Never prompt for missing values (fail instead)
        
    Returns:
        The transformed configuration
    """
    print_info(f"Processing config at path '{path}', type: {type(config)}")
    
    # For debugging, check if the config is a string with a tag prefix
    if isinstance(config, str) and (config.startswith('!developer_secret') or config.startswith('!user_secret')):
        print_warning(f"Found raw string with tag prefix at path '{path}': {config}")
        # This indicates a YAML parsing issue - tags should be objects, not strings
    if isinstance(config, DeveloperSecret):
        # Process developer secret
        value = config.value
        
        # Process OmegaConf-style environment variable references
        # This is where OmegaConf-style resolution happens, separate from Pydantic Settings
        if isinstance(value, str) and value.startswith('${oc.env:') and value.endswith('}'):
            env_var = value[9:-1]  # Extract VAR_NAME from ${oc.env:VAR_NAME}
            env_value = os.environ.get(env_var)
            if env_value is None:
                if no_prompt:
                    # Don't prompt - just warn and set empty string
                    print_warning(f"Environment variable {env_var} not found. (--no-prompt is set)")
                    env_value = ""
                else:
                    # Prompt the user for the missing value
                    print_warning(f"Environment variable {env_var} not found.")
                    env_value = typer.prompt(
                        f"Enter value for {env_var} (secret at {path})",
                        hide_input=True,
                        default="",
                        show_default=False
                    )
                    if not env_value:
                        print_warning(f"No value provided for {env_var}.")
            print_info(f"Resolved value for developer secret at {path}")
            value = env_value
            
        # Create the secret in the backend
        try:
            print_info(f"Creating developer secret at {path}...")
            # Developer secrets must have values
            if value is None or value == "":
                if no_prompt:
                    # Don't prompt - just fail immediately
                    error_msg = f"Developer secret at {path} has no value. Developer secrets must have values. (--no-prompt is set)"
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
                value=value
            )
            
            print_info(f"Created developer secret at path {path} with handle: {handle}")
            return handle
        except Exception as e:
            print_error(f"Failed to create developer secret at {path}: {str(e)}")
            raise
        
    elif isinstance(config, UserSecret):
        # For deploy phase, keep user secrets as-is
        # They will be processed during the configure phase
        print_info(f"Keeping user secret at {path} as-is for configure phase")
        return config
        
    elif isinstance(config, dict):
        # Process each key in the dictionary
        result = {}
        for key, value in config.items():
            new_path = f"{path}.{key}" if path else key
            result[key] = await transform_config_recursive(value, client, new_path, no_prompt)
        return result
        
    elif isinstance(config, list):
        # Process each item in the list
        result = []
        for i, value in enumerate(config):
            new_path = f"{path}[{i}]" if path else f"[{i}]"
            result.append(await transform_config_recursive(value, client, new_path, no_prompt))
        return result
        
    else:
        # Return primitive values as-is
        return config


async def compare_configs(original: Dict[Any, Any], transformed: Dict[Any, Any]) -> None:
    """Compare and print the differences between original and transformed configs.
    
    In deploy phase:
    - Developer secrets are transformed to UUID handles
    - User secrets are kept as-is
    
    Args:
        original: The original configuration
        transformed: The transformed configuration
    """
    print_info("\nSecret Transformations Summary:")
    
    # Track transformations for a summary table
    dev_transformations = []
    retained_user_secrets = []
    
    # This is a simplified comparison that shows replaced values and retained user secrets
    def walk_configs(orig: Any, trans: Any, path: str = "") -> None:
        if isinstance(orig, dict) and isinstance(trans, dict):
            for key in orig:
                if key in trans:
                    new_path = f"{path}.{key}" if path else key
                    walk_configs(orig[key], trans[key], new_path)
        elif isinstance(orig, list) and isinstance(trans, list):
            for i, (o, t) in enumerate(zip(orig, trans)):
                new_path = f"{path}[{i}]"
                walk_configs(o, t, new_path)
        else:
            # Developer secrets have been transformed to handles
            if isinstance(orig, DeveloperSecret) and isinstance(trans, str):
                dev_transformations.append((path, trans))
                print_info(f"Developer secret at {path} transformed to handle: {trans}")
            
            # User secrets remain as tags for the configure phase
            elif isinstance(orig, UserSecret) and isinstance(trans, UserSecret):
                retained_user_secrets.append(path)
                print_info(f"User secret at {path} retained for configure phase")
    
    # Walk through both configurations and find differences
    walk_configs(original, transformed)
    
    # Print summary
    if dev_transformations:
        print_info(f"\nTransformed {len(dev_transformations)} developer secret(s) to handles")
    else:
        print_warning("No developer secrets were found in the configuration")
        
    if retained_user_secrets:
        print_info(f"\nRetained {len(retained_user_secrets)} user secret(s) for configure phase")
    else:
        print_info("No user secrets were found in the configuration")