"""
YAML tag handling for MCP Agent Cloud secrets.

This module provides custom PyYAML handlers for the !developer_secret and !user_secret
custom tags, allowing proper serialization and deserialization of secret values.
"""

import re
import yaml
from yaml.loader import SafeLoader


class SecretBase(yaml.YAMLObject):
    """Base class for secret YAML tags."""
    
    def __init__(self, value=None):
        self.value = value
    
    @classmethod
    def from_yaml(cls, loader, node):
        # Handle both scalar values and empty tags
        if isinstance(node, yaml.ScalarNode):
            value = loader.construct_scalar(node)
            # Convert empty strings to None
            if value == '':
                return cls(None)
            return cls(value)
        return cls(None)
    
    def __repr__(self):
        return f"{self.__class__.__name__}(value={self.value})"


class UserSecret(SecretBase):
    """Custom YAML tag for user-provided secrets."""
    yaml_tag = u'!user_secret'


class DeveloperSecret(SecretBase):
    """Custom YAML tag for developer-provided secrets."""
    yaml_tag = u'!developer_secret'


# Custom YAML dumper that handles empty tags properly
class SecretYamlDumper(yaml.SafeDumper):
    """Custom YAML dumper that processes empty tags better."""
    
    def represent_scalar(self, tag, value, style=None):
        """Customize the representation of scalar values."""
        # For secret tags with empty strings, treat them specially
        if (tag in ['!user_secret', '!developer_secret']) and (value is None or value == ''):
            # Use an empty style (plain) for empty tags to remove the quotes
            return yaml.ScalarNode(tag, '', style='')
        
        # For all other cases, use the default behavior
        return super().represent_scalar(tag, value, style=style)


# For backward compatibility with tests
class EmptyTagDumper(yaml.SafeDumper):
    """Custom YAML dumper that only handles empty tags with no quotes.
    
    For tests, this class explicitly formats without quotes for compatibility.
    """
    def represent_scalar(self, tag, value, style=None):
        """Use plain style for all secret tags."""
        if tag in ['!user_secret', '!developer_secret']:
            # Use plain style (no quotes) for all secret tags
            return yaml.ScalarNode(tag, value, style='')
        return super().represent_scalar(tag, value, style=style)


# Register representation functions for our custom tag classes
def represent_user_secret(dumper, data):
    """Custom representation for UserSecret objects."""
    if data.value is None or data.value == '':
        # For empty values, use a tag with no content and plain style
        # This is the key fix - using '' as style removes the quotes
        return dumper.represent_scalar('!user_secret', '', style='')
    # For non-empty values, preserve them
    return dumper.represent_scalar('!user_secret', data.value)


def represent_developer_secret(dumper, data):
    """Custom representation for DeveloperSecret objects."""
    if data.value is None or data.value == '':
        # For empty values, use a tag with no content and plain style
        # Using '' as style removes the quotes
        return dumper.represent_scalar('!developer_secret', '', style='')
    # For non-empty values, preserve them
    return dumper.represent_scalar('!developer_secret', data.value)


# Create a custom YAML loader
class SecretYamlLoader(SafeLoader):
    """Custom YAML loader that understands the secret tags."""
    pass


# Register constructors with the loader
def construct_user_secret(loader, node):
    """Constructor for !user_secret tags."""
    return UserSecret.from_yaml(loader, node)


def construct_developer_secret(loader, node):
    """Constructor for !developer_secret tags."""
    return DeveloperSecret.from_yaml(loader, node)


SecretYamlLoader.add_constructor('!user_secret', construct_user_secret)
SecretYamlLoader.add_constructor('!developer_secret', construct_developer_secret)

# Register representers with the dumper
SecretYamlDumper.add_representer(UserSecret, represent_user_secret)
SecretYamlDumper.add_representer(DeveloperSecret, represent_developer_secret)

# Register representers with EmptyTagDumper as well
EmptyTagDumper.add_representer(UserSecret, represent_user_secret)
EmptyTagDumper.add_representer(DeveloperSecret, represent_developer_secret)


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
    
    # Post-process to remove empty quotes for cleaner output in case the custom style doesn't work
    # This addresses a PyYAML limitation where custom tags with empty values
    # are always represented with empty quotes (''), which we don't want.
    # We want !user_secret and not !user_secret ''
    return re.sub(r'(!user_secret|!developer_secret) [\'\"][\'\"]', r'\1', yaml_str)