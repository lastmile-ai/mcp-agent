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

# Register YAML tag constructors for testing
yaml.SafeLoader.add_constructor('!developer_secret', lambda loader, node: DeveloperSecret(loader.construct_scalar(node)))
yaml.SafeLoader.add_constructor('!user_secret', lambda loader, node: UserSecret())
yaml.FullLoader.add_constructor('!developer_secret', lambda loader, node: DeveloperSecret(loader.construct_scalar(node)))
yaml.FullLoader.add_constructor('!user_secret', lambda loader, node: UserSecret())
from mcp_agent_cloud.secrets.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return UUIDs or prefixed handles
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a deterministic UUID-like string based on name
        # This uses a proper UUID format for testing
        import hashlib
        import uuid
        
        # Create a deterministic UUID based on the name
        name_hash = hashlib.md5(name.encode()).hexdigest()
        generated_uuid = str(uuid.UUID(name_hash))
        
        # Return the UUID (current API behavior) - we support both formats
        return generated_uuid
    
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
    
    # Check the result is a valid handle (UUID format)
    from mcp_agent_cloud.secrets.constants import HANDLE_PATTERN
    assert HANDLE_PATTERN.match(result), f"Expected valid handle format, got: {result}"
    
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
    
    # User secrets remain as UserSecret objects during deploy phase
    assert isinstance(result, UserSecret)
    
    # Client should not be called for user secrets during deploy phase
    mock_secrets_client.create_secret.assert_not_called()


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
    
    # Check the developer secret is replaced with valid handle
    from mcp_agent_cloud.secrets.constants import HANDLE_PATTERN
    assert HANDLE_PATTERN.match(result["server"]["bedrock"]["api_key"]), \
        f"Expected valid handle format, got: {result['server']['bedrock']['api_key']}"
    
    # Check the user secret remains as UserSecret
    assert isinstance(result["server"]["bedrock"]["user_access_key"], UserSecret), \
        f"Expected UserSecret, got: {type(result['server']['bedrock']['user_access_key'])}"
    
    # Verify client was called once (only for developer secret)
    assert mock_secrets_client.create_secret.call_count == 1


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
    
    # Check the developer secret is replaced with valid handle
    from mcp_agent_cloud.secrets.constants import HANDLE_PATTERN
    assert HANDLE_PATTERN.match(result_yaml["server"]["bedrock"]["api_key"]), \
        f"Expected valid handle format, got: {result_yaml['server']['bedrock']['api_key']}"
    
    # Check user secret is still a tag (PyYAML should load it as a UserSecret)
    assert isinstance(result_yaml["server"]["bedrock"]["user_access_key"], UserSecret), \
        f"Expected UserSecret, got: {type(result_yaml['server']['bedrock']['user_access_key'])}"
    
    # Verify client was called once (only for developer secret)
    assert mock_secrets_client.create_secret.call_count == 1


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
    
    # Check the result is a valid handle (UUID format)
    from mcp_agent_cloud.secrets.constants import HANDLE_PATTERN
    assert HANDLE_PATTERN.match(result), f"Expected valid handle format, got: {result}"
    
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
    
    # Check developer secret is replaced with handle
    assert isinstance(transformed_yaml["server"]["bedrock"]["api_key"], str)
    # The exact format depends on the mock implementation, but it should be a string
    
    # Check user secret remains as UserSecret
    assert isinstance(transformed_yaml["server"]["bedrock"]["user_access_key"], UserSecret)
    
    # Verify client was called once (only for developer secret)
    assert mock_secrets_client.create_secret.call_count == 1