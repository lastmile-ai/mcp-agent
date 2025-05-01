"""Tests for YAML post-processing functionality.

This module tests the regex post-processing approach for fixing empty quotes in YAML.
"""

import pytest
import yaml
import re
from yaml.loader import SafeLoader

# Define classes to represent our custom YAML tags
class UserSecret:
    def __init__(self, value=None):
        self.value = value
    
    def __repr__(self):
        return f"UserSecret(value={self.value})"

class DeveloperSecret:
    def __init__(self, value=None):
        self.value = value
    
    def __repr__(self):
        return f"DeveloperSecret(value={self.value})"

# Custom constructors for loading
def construct_user_secret(loader, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        # Convert empty strings to None
        if value == '':
            return UserSecret(None)
        return UserSecret(value)
    # Handle the case where there's no value after the tag
    return UserSecret(None)

def construct_developer_secret(loader, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        # Convert empty strings to None
        if value == '':
            return DeveloperSecret(None)
        return DeveloperSecret(value)
    # Handle the case where there's no value after the tag
    return DeveloperSecret(None)

# Custom representers for dumping
def represent_user_secret(dumper, data):
    if data.value is None or data.value == '':
        # We still need an empty string here, but we'll post-process it
        return dumper.represent_scalar('!user_secret', '')
    return dumper.represent_scalar('!user_secret', data.value)

def represent_developer_secret(dumper, data):
    if data.value is None or data.value == '':
        # We still need an empty string here, but we'll post-process it
        return dumper.represent_scalar('!developer_secret', '')
    return dumper.represent_scalar('!developer_secret', data.value)

# Custom loader
class CustomLoader(SafeLoader):
    pass

# Register our constructors with the CustomLoader
CustomLoader.add_constructor('!user_secret', construct_user_secret)
CustomLoader.add_constructor('!developer_secret', construct_developer_secret)

# Custom dumper
class CustomDumper(yaml.SafeDumper):
    pass

# Register our representers with the CustomDumper
CustomDumper.add_representer(UserSecret, represent_user_secret)
CustomDumper.add_representer(DeveloperSecret, represent_developer_secret)


def test_post_process_empty_quotes():
    """Test post-processing regex to remove empty quotes from tags."""
    # Test data
    config = {
        'server': {
            'api_key': DeveloperSecret('some-value'),
            'empty_dev_secret': DeveloperSecret(),
            'user_token': UserSecret('user-value'),
            'empty_user_secret': UserSecret()
        }
    }
    
    # Dump to YAML
    yaml_str = yaml.dump(config, Dumper=CustomDumper, default_flow_style=False)
    
    # Post-process to remove empty quotes using single quote pattern
    fixed_yaml = re.sub(r'(!user_secret|!developer_secret) \'\'', r'\1', yaml_str)
    
    # Verify single quotes are removed from empty tags
    assert "empty_dev_secret: !developer_secret ''" not in fixed_yaml
    assert "empty_dev_secret: !developer_secret" in fixed_yaml
    assert "empty_user_secret: !user_secret ''" not in fixed_yaml
    assert "empty_user_secret: !user_secret" in fixed_yaml
    
    # Verify tags with values still have their values
    assert "api_key: !developer_secret 'some-value'" in fixed_yaml
    assert "user_token: !user_secret 'user-value'" in fixed_yaml


def test_regex_works_with_both_quote_types():
    """Test that the regex works with both single and double quotes."""
    yaml_with_single_quotes = """
server:
  empty_dev_secret: !developer_secret ''
  empty_user_secret: !user_secret ''
"""
    
    yaml_with_double_quotes = """
server:
  empty_dev_secret: !developer_secret ""
  empty_user_secret: !user_secret ""
"""
    
    # Regex that handles both types of quotes
    combined_regex = r'(!user_secret|!developer_secret) [\'\"][\'\"]'
    
    # Fix single quotes
    fixed_single = re.sub(combined_regex, r'\1', yaml_with_single_quotes)
    assert "empty_dev_secret: !developer_secret" in fixed_single
    assert "empty_user_secret: !user_secret" in fixed_single
    assert "''" not in fixed_single
    
    # Fix double quotes
    fixed_double = re.sub(combined_regex, r'\1', yaml_with_double_quotes)
    assert "empty_dev_secret: !developer_secret" in fixed_double
    assert "empty_user_secret: !user_secret" in fixed_double
    assert '""' not in fixed_double


def test_round_trip_with_post_processing():
    """Test full round-trip serialization and deserialization with post-processing."""
    # Test data
    config = {
        'server': {
            'api_key': DeveloperSecret('test-key'),
            'empty_user_secret': UserSecret()
        }
    }
    
    # Dump to YAML
    yaml_str = yaml.dump(config, Dumper=CustomDumper, default_flow_style=False)
    
    # Post-process to remove empty quotes
    fixed_yaml = re.sub(r'(!user_secret|!developer_secret) [\'\"][\'\"]', r'\1', yaml_str)
    
    # Verify format
    assert "empty_user_secret: !user_secret" in fixed_yaml
    assert "empty_user_secret: !user_secret ''" not in fixed_yaml
    assert "api_key: !developer_secret 'test-key'" in fixed_yaml
    
    # Load back
    loaded = yaml.load(fixed_yaml, Loader=CustomLoader)
    
    # Verify the loaded objects
    assert isinstance(loaded, dict)
    assert 'server' in loaded
    assert isinstance(loaded['server']['api_key'], DeveloperSecret)
    assert loaded['server']['api_key'].value == 'test-key'
    assert isinstance(loaded['server']['empty_user_secret'], UserSecret)
    assert loaded['server']['empty_user_secret'].value is None