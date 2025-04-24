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

from ..config import settings
from .constants import SecretType
from .api_client import SecretsClient
from ..ux import print_info, print_warning, print_error


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


async def process_config_secrets(
    config_path: Union[str, Path],
    output_path: Union[str, Path],
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
) -> None:
    """Process a configuration file, transforming secret tags to handles.
    
    Args:
        config_path: Path to the configuration file
        output_path: Path to write the transformed configuration to
        api_url: Optional Secrets API URL, overrides environment variable
        api_token: Optional Secrets API token, overrides environment variable
    
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
    
    # Initialize the secrets client
    client = SecretsClient(
        api_url=api_url or settings.SECRETS_API_URL,
        api_token=api_token or settings.SECRETS_API_TOKEN
    )
    
    # Process the configuration file for secrets
    transformed_str = await process_secrets_in_config(config_str, client)
    
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
    client: SecretsClient
) -> str:
    """Process secrets in the configuration string.
    
    Args:
        config_str: The configuration string containing secret tags
        client: The secrets client to use for creating secrets
    
    Returns:
        The transformed configuration string with secret tags replaced by handles
    """
    # Load the config with custom tag handlers
    config_yaml = yaml.load(config_str, Loader=yaml.FullLoader)
    
    # Process the loaded YAML recursively
    transformed_yaml = await transform_config_recursive(config_yaml, client)
    
    # Convert back to YAML string
    transformed_str = yaml.dump(transformed_yaml, default_flow_style=False)
    
    return transformed_str


async def transform_config_recursive(
    config: Any, 
    client: SecretsClient, 
    path: str = ""
) -> Any:
    """Recursively transform a config dictionary, replacing secrets with handles.
    
    Args:
        config: The configuration dictionary/value to transform
        client: The secrets client
        path: The current path in the config (for naming secrets)
        
    Returns:
        The transformed configuration
    """
    if isinstance(config, DeveloperSecret):
        # Process developer secret
        value = config.value
        
        # Process OmegaConf-style environment variable references
        # This is where OmegaConf-style resolution happens, separate from Pydantic Settings
        if isinstance(value, str) and value.startswith('${oc.env:') and value.endswith('}'):
            env_var = value[9:-1]  # Extract VAR_NAME from ${oc.env:VAR_NAME}
            env_value = os.environ.get(env_var)
            if env_value is None:
                print_warning(f"Environment variable {env_var} not found. Using empty string.")
                env_value = ""
            print_info(f"Resolved environment variable {env_var} for developer secret at {path}")
            value = env_value
            
        # Create the secret in the backend
        try:
            print_info(f"Creating developer secret at {path}...")
            handle = await client.create_secret(
                name=path or "unknown.path",
                secret_type=SecretType.DEVELOPER,
                value=value
            )
            
            print_info(f"Created developer secret at path {path} with handle {handle}")
            return handle
        except Exception as e:
            print_error(f"Failed to create developer secret at {path}: {str(e)}")
            raise
        
    elif isinstance(config, UserSecret):
        # Process user secret
        try:
            print_info(f"Creating user secret placeholder at {path}...")
            handle = await client.create_secret(
                name=path or "unknown.path",
                secret_type=SecretType.USER,
                value=None
            )
            
            print_info(f"Created user secret placeholder at path {path} with handle {handle}")
            return handle
        except Exception as e:
            print_error(f"Failed to create user secret at {path}: {str(e)}")
            raise
        
    elif isinstance(config, dict):
        # Process each key in the dictionary
        result = {}
        for key, value in config.items():
            new_path = f"{path}.{key}" if path else key
            result[key] = await transform_config_recursive(value, client, new_path)
        return result
        
    elif isinstance(config, list):
        # Process each item in the list
        result = []
        for i, value in enumerate(config):
            new_path = f"{path}[{i}]" if path else f"[{i}]"
            result.append(await transform_config_recursive(value, client, new_path))
        return result
        
    else:
        # Return primitive values as-is
        return config


async def compare_configs(original: Dict[Any, Any], transformed: Dict[Any, Any]) -> None:
    """Compare and print the differences between original and transformed configs.
    
    Args:
        original: The original configuration
        transformed: The transformed configuration
    """
    print_info("\nSecret Transformations Summary:")
    
    # Track transformations for a summary table
    transformations = []
    
    # This is a simplified comparison that just shows replaced values
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
            # If values are different, it might be a transformed secret
            if orig != trans and isinstance(trans, str) and trans.startswith("mcpac_"):
                # Determine secret type from handle prefix
                if "dev_" in trans:
                    secret_type = SecretType.DEVELOPER
                else:
                    secret_type = SecretType.USER
                
                # Add to our list of transformations
                transformations.append((path, secret_type, trans))
                
                # Print individual transformation
                print_info(f"Secret at {path} ({secret_type.value}) transformed to handle: {trans}")
    
    # Walk through both configurations and find differences
    walk_configs(original, transformed)
    
    if not transformations:
        print_warning("No secrets were transformed in the configuration.")