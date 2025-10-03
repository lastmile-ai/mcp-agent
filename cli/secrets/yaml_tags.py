"""
YAML tag handling for MCP Agent Cloud secrets.

This module provides custom PyYAML handlers for the !developer_secret and !user_secret
custom tags, allowing proper serialization and deserialization of secret values.
"""

import re

import yaml
from yaml.loader import SafeLoader


class SecretTag:
    """Base class for secret tag objects."""

    def __init__(self, value=None):
        self.value = value

    def __repr__(self):
        return f"{self.__class__.__name__}(value={self.value})"


class UserSecret(SecretTag):
    """Represents a !user_secret tag in YAML."""

    pass


class DeveloperSecret(SecretTag):
    """Represents a !developer_secret tag in YAML."""

    pass


def construct_user_secret(loader, node):
    """Constructor for !user_secret tags."""
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        # Convert empty strings to None
        if value == "":
            return UserSecret(None)
        return UserSecret(value)
    # Handle the case where there's no value after the tag
    return UserSecret(None)


def construct_developer_secret(loader, node):
    """Constructor for !developer_secret tags."""
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        # Convert empty strings to None
        if value == "":
            return DeveloperSecret(None)
        return DeveloperSecret(value)
    # Handle the case where there's no value after the tag
    return DeveloperSecret(None)


def represent_user_secret(dumper, data):
    """Representer for UserSecret objects when dumping to YAML."""
    if data.value is None or data.value == "":
        # Empty value is represented with empty quotes, will be post-processed
        return dumper.represent_scalar("!user_secret", "")
    return dumper.represent_scalar("!user_secret", data.value)


def represent_developer_secret(dumper, data):
    """Representer for DeveloperSecret objects when dumping to YAML."""
    if data.value is None or data.value == "":
        # Empty value is represented with empty quotes, will be post-processed
        return dumper.represent_scalar("!developer_secret", "")
    return dumper.represent_scalar("!developer_secret", data.value)


class SecretYamlLoader(SafeLoader):
    """Custom YAML loader that understands the secret tags."""

    pass


class SecretYamlDumper(yaml.SafeDumper):
    """Custom YAML dumper that properly formats secret tags."""

    pass


# Register constructors with the loader
SecretYamlLoader.add_constructor("!user_secret", construct_user_secret)
SecretYamlLoader.add_constructor("!developer_secret", construct_developer_secret)

# Register representers with the dumper
SecretYamlDumper.add_representer(UserSecret, represent_user_secret)
SecretYamlDumper.add_representer(DeveloperSecret, represent_developer_secret)


def load_yaml_with_secrets(yaml_str):
    """
    Load YAML string containing secret tags into Python objects.

    Args:
        yaml_str: YAML string that may contain !user_secret or !developer_secret tags

    Returns:
        Parsed Python object with UserSecret and DeveloperSecret objects
    """
    return yaml.load(yaml_str, Loader=SecretYamlLoader)


def dump_yaml_with_secrets(data):
    """
    Dump Python objects to YAML string, properly handling secret tags.

    Args:
        data: Python object that may contain UserSecret or DeveloperSecret objects

    Returns:
        YAML string with proper secret tags
    """
    yaml_str = yaml.dump(data, Dumper=SecretYamlDumper, default_flow_style=False)

    # Post-process to remove empty quotes for cleaner output
    # This addresses a PyYAML limitation where custom tags with empty values
    # are always represented with empty quotes (''), which we don't want.
    # We want !user_secret and not !user_secret ''
    return re.sub(r"(!user_secret|!developer_secret) \'\'", r"\1", yaml_str)
