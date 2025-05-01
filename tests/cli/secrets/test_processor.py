"""Tests for the secrets processor."""

import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent_cloud.secrets.processor import (
    process_secrets_in_config,
    transform_config_recursive
)
from mcp_agent_cloud.secrets.constants import SecretType


@pytest.fixture
def mock_secrets_client():
    """Mock secrets client for testing."""
    client = AsyncMock()
    # Set up responses for method calls
    client.create_secret.return_value = "mcpac_dev_12345678-abcd-1234-efgh-123456789abc"
    return client


@pytest.mark.asyncio
async def test_process_secrets_in_config_empty_tags(mock_secrets_client):
    """Test the process_secrets_in_config function with empty tags."""
    yaml_content = """
server:
  bedrock:
    api_key: !developer_secret my-api-key
    user_api_key: !user_secret
"""
    
    # Process the YAML content
    result = await process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=True)
    
    # The output should have developer_secret replaced with a handle
    # and user_secret kept as-is but without quotes
    assert "api_key: mcpac_dev_12345678-abcd-1234-efgh-123456789abc" in result
    
    # Check that user_secret is kept as !user_secret (no quotes after tag)
    assert "user_api_key: !user_secret" in result
    assert "user_api_key: !user_secret ''" not in result


@pytest.mark.asyncio
async def test_process_secrets_in_config_with_values(mock_secrets_client):
    """Test the process_secrets_in_config function with values."""
    yaml_content = """
server:
  bedrock:
    api_key: !developer_secret my-api-key
"""
    
    # Process the YAML content
    result = await process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=True)
    
    # The output should have developer_secret replaced with a handle
    assert "api_key: mcpac_dev_12345678-abcd-1234-efgh-123456789abc" in result
    
    # The mock client should have been called with the right values
    mock_secrets_client.create_secret.assert_called_once_with(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="my-api-key"
    )


@pytest.mark.asyncio
async def test_process_secrets_in_config_regex_fixes_empty_quotes(mock_secrets_client):
    """Test that the regex post-processing removes empty quotes from tags."""
    # Create a mock EmptyTagDumper that doesn't actually fix the quotes
    # This will help us verify the regex post-processing
    with patch('mcp_agent_cloud.secrets.processor.EmptyTagDumper') as mock_dumper:
        # Make the dumper return quotes that need to be post-processed
        def mock_dump(transformed_yaml, **kwargs):
            # This will produce YAML with quotes
            return """server:
  bedrock:
    api_key: mcpac_dev_12345678-abcd-1234-efgh-123456789abc
    user_api_key: !user_secret ''
"""
        
        # Replace yaml.dump with our mock
        with patch('yaml.dump', mock_dump):
            yaml_content = """
server:
  bedrock:
    api_key: !developer_secret my-api-key
    user_api_key: !user_secret
"""
            
            # Process the YAML content
            result = await process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=True)
            
            # Verify the post-processing works
            assert "user_api_key: !user_secret" in result
            assert "user_api_key: !user_secret ''" not in result