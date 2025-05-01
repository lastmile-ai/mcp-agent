"""Tests for YAML tag handling and post-processing for MCP Agent Cloud secrets."""

import yaml
import re
import pytest
from unittest import TestCase

from mcp_agent_cloud.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    EmptyTagDumper,
    represent_user_secret,
    represent_developer_secret,
    load_yaml_with_secrets,
    dump_yaml_with_secrets,
)


class TestYamlSecretTags(TestCase):
    """Test handling of YAML tags for secrets."""

    def test_basic_round_trip(self):
        """Test that secrets objects can be round-tripped through YAML."""
        # Create a simple config with both types of secrets
        config = {
            'server': {
                'api_key': DeveloperSecret('dev-api-key'),
                'user_token': UserSecret('user-token'),
            }
        }
        
        # Dump the config to a YAML string using our custom dumper
        yaml_str = dump_yaml_with_secrets(config)
        
        # Check the string has the expected tags
        # The actual format may have quotes depending on the YAML implementation
        assert '!developer_secret' in yaml_str and 'dev-api-key' in yaml_str
        assert '!user_secret' in yaml_str and 'user-token' in yaml_str
        
        # Load the string back using our custom loader
        loaded = load_yaml_with_secrets(yaml_str)
        
        # Verify the objects are reconstructed correctly
        assert isinstance(loaded['server']['api_key'], DeveloperSecret)
        assert loaded['server']['api_key'].value == 'dev-api-key'
        assert isinstance(loaded['server']['user_token'], UserSecret)
        assert loaded['server']['user_token'].value == 'user-token'

    def test_empty_tags(self):
        """Test YAML handling of empty tags (no value)."""
        # Create a config with empty tags
        config = {
            'server': {
                'api_key': DeveloperSecret(),  # No value
                'user_token': UserSecret(),    # No value
            }
        }
        
        # Dump the config using our custom dumper (handles empty quotes automatically)
        yaml_str = dump_yaml_with_secrets(config)
        
        # Check for tags without values
        assert '!developer_secret' in yaml_str
        assert '!user_secret' in yaml_str
        
        # Make sure no empty quotes remain
        assert not ('!developer_secret ""' in yaml_str or "!developer_secret ''" in yaml_str)
        assert not ('!user_secret ""' in yaml_str or "!user_secret ''" in yaml_str)
        
        # Load the string back using our custom loader
        loaded = load_yaml_with_secrets(yaml_str)
        
        # Verify the objects with None values
        assert isinstance(loaded['server']['api_key'], DeveloperSecret)
        assert loaded['server']['api_key'].value is None
        assert isinstance(loaded['server']['user_token'], UserSecret)
        assert loaded['server']['user_token'].value is None

    def test_nested_structure(self):
        """Test handling of secrets in deeply nested structures."""
        # Create a complex config with nested structure
        config = {
            'server': {
                'providers': {
                    'bedrock': {
                        'api_key': DeveloperSecret('bedrock-key'),
                        'region': 'us-west-2',
                    },
                    'openai': {
                        'api_key': UserSecret('openai-key'),
                        'org_id': 'org-123',
                    }
                },
                'database': {
                    'password': DeveloperSecret('db-password'),
                    'user_password': UserSecret('user-db-password'),
                }
            }
        }
        
        # Dump and load using our custom functions
        yaml_str = dump_yaml_with_secrets(config)
        loaded = load_yaml_with_secrets(yaml_str)
        
        # Verify nested structure is preserved with correct types
        assert isinstance(loaded['server']['providers']['bedrock']['api_key'], DeveloperSecret)
        assert loaded['server']['providers']['bedrock']['api_key'].value == 'bedrock-key'
        assert loaded['server']['providers']['bedrock']['region'] == 'us-west-2'
        
        assert isinstance(loaded['server']['providers']['openai']['api_key'], UserSecret)
        assert loaded['server']['providers']['openai']['api_key'].value == 'openai-key'
        
        assert isinstance(loaded['server']['database']['password'], DeveloperSecret)
        assert isinstance(loaded['server']['database']['user_password'], UserSecret)

    def test_integration_with_standard_yaml(self):
        """Test integration with standard YAML values and structures."""
        # Create a config with a mix of secrets and standard YAML types
        config = {
            'server': {
                'api_key': DeveloperSecret('dev-api-key'),
                'port': 8080,
                'debug': True,
                'tags': ['prod', 'us-west'],
                'metadata': {
                    'created_at': '2023-01-01',
                    'created_by': UserSecret('user-123'),
                }
            }
        }
        
        # Dump and load using our custom functions
        yaml_str = dump_yaml_with_secrets(config)
        loaded = load_yaml_with_secrets(yaml_str)
        
        # Verify standard YAML values
        assert loaded['server']['port'] == 8080
        assert loaded['server']['debug'] is True
        assert loaded['server']['tags'] == ['prod', 'us-west']
        assert loaded['server']['metadata']['created_at'] == '2023-01-01'
        
        # Verify secrets
        assert isinstance(loaded['server']['api_key'], DeveloperSecret)
        assert isinstance(loaded['server']['metadata']['created_by'], UserSecret)


def test_post_process_empty_quotes():
    """Test that post-processing correctly removes empty quotes from tags."""
    yaml_str = """
server:
  empty_dev_secret: !developer_secret ""
  empty_user_secret: !user_secret ""
  dev_with_value: !developer_secret "API_KEY"
  user_with_value: !user_secret "USER_KEY"
"""
    
    # Apply the post-processing regex
    processed = re.sub(r'(!user_secret|!developer_secret) [\'\"][\'\"]', r'\1', yaml_str)
    
    # Check the result
    assert '!developer_secret ""' not in processed
    assert '!user_secret ""' not in processed
    assert 'empty_dev_secret: !developer_secret' in processed
    assert 'empty_user_secret: !user_secret' in processed
    
    # Values should be preserved
    assert 'dev_with_value: !developer_secret "API_KEY"' in processed
    assert 'user_with_value: !user_secret "USER_KEY"' in processed


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
    
    # Process both strings
    processed_single = re.sub(combined_regex, r'\1', yaml_with_single_quotes)
    processed_double = re.sub(combined_regex, r'\1', yaml_with_double_quotes)
    
    # Check results for both quote types
    assert '!developer_secret \'\'' not in processed_single
    assert '!user_secret \'\'' not in processed_single
    assert '!developer_secret ""' not in processed_double
    assert '!user_secret ""' not in processed_double


def test_real_world_example():
    """Test with a real-world example from the CLAUDE.md design doc."""
    # Example from the CLAUDE.md design document
    yaml_str = """
# $schema: ...
server:
  bedrock:
    # Value comes from env var BEDROCK_KEY
    api_key: !developer_secret BEDROCK_KEY
    # Value collected during configure, env var USER_KEY is an override
    user_access_key: !user_secret USER_KEY 
database:
  # Must be prompted for during deploy if non-interactive is false
  password: !developer_secret 
"""
    
    # Load the string using our custom loader
    loaded = load_yaml_with_secrets(yaml_str)
    
    # Verify the structure and tags
    assert isinstance(loaded['server']['bedrock']['api_key'], DeveloperSecret)
    assert loaded['server']['bedrock']['api_key'].value == 'BEDROCK_KEY'
    assert isinstance(loaded['server']['bedrock']['user_access_key'], UserSecret)
    assert loaded['server']['bedrock']['user_access_key'].value == 'USER_KEY'
    assert isinstance(loaded['database']['password'], DeveloperSecret)
    assert loaded['database']['password'].value is None
    
    # Test the full round-trip using our custom functions
    dumped = dump_yaml_with_secrets(loaded)
    
    # Re-load the processed YAML
    reloaded = load_yaml_with_secrets(dumped)
    
    # Verify again
    assert isinstance(reloaded['server']['bedrock']['api_key'], DeveloperSecret)
    assert reloaded['server']['bedrock']['api_key'].value == 'BEDROCK_KEY'
    assert isinstance(reloaded['server']['bedrock']['user_access_key'], UserSecret)
    assert reloaded['server']['bedrock']['user_access_key'].value == 'USER_KEY'
    assert isinstance(reloaded['database']['password'], DeveloperSecret)
    # Empty tag should remain empty after round-trip
    assert reloaded['database']['password'].value is None