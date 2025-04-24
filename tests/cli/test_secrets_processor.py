"""Tests for the secrets processor."""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import yaml

from mcp_agent_cloud.secrets.processor import (
    process_config_secrets,
    process_secrets_in_config,
    transform_config_recursive,
    DeveloperSecret,
    UserSecret
)
from mcp_agent_cloud.secrets.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return different handles for dev/user secrets
    async def mock_create_secret(name, secret_type, value=None):
        if secret_type == SecretType.DEVELOPER:
            return f"mcpac_dev_{name.replace('.', '_')}"
        else:
            return f"mcpac_usr_{name.replace('.', '_')}"
    
    client.create_secret.side_effect = mock_create_secret
    
    # Configure get_secret_value
    client.get_secret_value.return_value = "test-secret-value"
    
    return client


@pytest.mark.asyncio
async def test_transform_config_recursive_developer_secret(mock_secrets_client):
    """Test transforming a developer secret."""
    # Create a config with a developer secret
    dev_secret = DeveloperSecret("test-api-key")
    
    # Transform the secret
    result = await transform_config_recursive(
        dev_secret,
        mock_secrets_client,
        "server.bedrock.api_key"
    )
    
    # Check the result is the handle
    assert result == "mcpac_dev_server_bedrock_api_key"
    
    # Verify client was called correctly
    mock_secrets_client.create_secret.assert_called_once_with(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="test-api-key"
    )


@pytest.mark.asyncio
async def test_transform_config_recursive_user_secret(mock_secrets_client):
    """Test transforming a user secret."""
    # Create a config with a user secret
    user_secret = UserSecret()
    
    # Transform the secret
    result = await transform_config_recursive(
        user_secret,
        mock_secrets_client,
        "server.bedrock.user_access_key"
    )
    
    # Check the result is the handle
    assert result == "mcpac_usr_server_bedrock_user_access_key"
    
    # Verify client was called correctly
    mock_secrets_client.create_secret.assert_called_once_with(
        name="server.bedrock.user_access_key",
        secret_type=SecretType.USER,
        value=None
    )


@pytest.mark.asyncio
async def test_transform_config_recursive_nested(mock_secrets_client):
    """Test transforming a nested config."""
    # Create a nested config with secrets
    config = {
        "server": {
            "bedrock": {
                "api_key": DeveloperSecret("test-api-key"),
                "user_access_key": UserSecret()
            }
        }
    }
    
    # Transform the config
    result = await transform_config_recursive(
        config,
        mock_secrets_client
    )
    
    # Check the structure is preserved
    assert "server" in result
    assert "bedrock" in result["server"]
    
    # Check the secrets are replaced with handles
    assert result["server"]["bedrock"]["api_key"] == "mcpac_dev_server_bedrock_api_key"
    assert result["server"]["bedrock"]["user_access_key"] == "mcpac_usr_server_bedrock_user_access_key"
    
    # Verify client was called twice
    assert mock_secrets_client.create_secret.call_count == 2


@pytest.mark.asyncio
async def test_process_secrets_in_config(mock_secrets_client, tmp_path):
    """Test processing secrets in a config string."""
    # Create a config with secrets
    config_str = """
server:
  bedrock:
    default_model: anthropic.claude-3-haiku-20240307-v1:0
    api_key: !developer_secret test-api-key
    user_access_key: !user_secret
"""
    
    # Process the config
    result = await process_secrets_in_config(config_str, mock_secrets_client)
    
    # Parse the result
    result_yaml = yaml.safe_load(result)
    
    # Check the structure is preserved
    assert "server" in result_yaml
    assert "bedrock" in result_yaml["server"]
    assert "default_model" in result_yaml["server"]["bedrock"]
    
    # Check the secrets are replaced with handles
    assert result_yaml["server"]["bedrock"]["api_key"] == "mcpac_dev_server_bedrock_api_key"
    assert result_yaml["server"]["bedrock"]["user_access_key"] == "mcpac_usr_server_bedrock_user_access_key"
    
    # Verify client was called twice
    assert mock_secrets_client.create_secret.call_count == 2


@pytest.mark.asyncio
async def test_env_var_resolution(mock_secrets_client, monkeypatch):
    """Test resolving environment variables in developer secrets."""
    # Set an environment variable
    monkeypatch.setenv("TEST_API_KEY", "env-var-value")
    
    # Create a config with an environment variable reference
    dev_secret = DeveloperSecret("${oc.env:TEST_API_KEY}")
    
    # Transform the secret
    result = await transform_config_recursive(
        dev_secret,
        mock_secrets_client,
        "server.bedrock.api_key"
    )
    
    # Check the result is the handle
    assert result == "mcpac_dev_server_bedrock_api_key"
    
    # Verify client was called correctly with resolved value
    mock_secrets_client.create_secret.assert_called_once_with(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="env-var-value"
    )


@pytest.mark.asyncio
async def test_process_config_secrets(mock_secrets_client, tmp_path, monkeypatch):
    """Test processing a config file."""
    # Create a temporary config file
    config_path = tmp_path / "config.yaml"
    config_str = """
server:
  bedrock:
    default_model: anthropic.claude-3-haiku-20240307-v1:0
    api_key: !developer_secret test-api-key
    user_access_key: !user_secret
"""
    config_path.write_text(config_str)
    
    # Create a temporary output file
    output_path = tmp_path / "transformed_config.yaml"
    
    # Mock the settings
    api_url = "http://example.com/api"
    api_token = "test-token"
    
    # Patch the SecretsClient class to return our mock
    with patch("mcp_agent_cloud.secrets.processor.SecretsClient", return_value=mock_secrets_client):
        # Process the config
        await process_config_secrets(
            config_path=str(config_path),
            output_path=str(output_path),
            api_url=api_url,
            api_token=api_token
        )
    
    # Check the output file exists
    assert output_path.exists()
    
    # Parse the output
    transformed_yaml = yaml.safe_load(output_path.read_text())
    
    # Check the structure is preserved
    assert "server" in transformed_yaml
    assert "bedrock" in transformed_yaml["server"]
    assert "default_model" in transformed_yaml["server"]["bedrock"]
    
    # Check the secrets are replaced with handles
    assert transformed_yaml["server"]["bedrock"]["api_key"] == "mcpac_dev_server_bedrock_api_key"
    assert transformed_yaml["server"]["bedrock"]["user_access_key"] == "mcpac_usr_server_bedrock_user_access_key"
    
    # Verify client was called for each secret
    assert mock_secrets_client.create_secret.call_count == 2