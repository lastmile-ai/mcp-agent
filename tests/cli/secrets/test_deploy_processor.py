"""Tests for the config secrets processor in deploy phase."""

import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent_cloud.secrets.processor import (
    transform_config_recursive,
    process_secrets_in_config,
    DeveloperSecret,
    UserSecret
)
from mcp_agent_cloud.secrets.constants import SecretType


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = MagicMock()
    
    # Mock the create_secret method to return UUIDs based on type
    async def mock_create_secret(name, secret_type, value):
        # Check that value is required for all secret types
        if value is None or value.strip() == "":
            raise ValueError(f"Secret '{name}' requires a non-empty value")
            
        # Create predictable but unique UUIDs for testing
        if secret_type == SecretType.DEVELOPER:
            return f"12345678-abcd-1234-efgh-dev-{name.replace('.', '-')}"
        elif secret_type == SecretType.USER:
            return f"98765432-wxyz-9876-abcd-usr-{name.replace('.', '-')}"
        else:
            raise ValueError(f"Invalid secret type: {secret_type}")
    
    client.create_secret = AsyncMock(side_effect=mock_create_secret)
    return client


@pytest.mark.asyncio
async def test_transform_config_recursive_developer_secret(mock_secrets_client):
    """Test transforming developer secrets to UUIDs."""
    # Create a config with a developer secret
    config = {
        "api": {
            "key": DeveloperSecret("test-api-key")
        }
    }
    
    # Transform the config
    result = await transform_config_recursive(config, mock_secrets_client)
    
    # Verify the result
    assert "api" in result
    assert "key" in result["api"]
    
    # Developer secret should be replaced with UUID
    dev_uuid = result["api"]["key"]
    assert isinstance(dev_uuid, str)
    assert dev_uuid.startswith("12345678-abcd-1234-efgh-dev-")
    
    # Verify create_secret was called with correct parameters
    mock_secrets_client.create_secret.assert_called_once_with(
        name="api.key",
        secret_type=SecretType.DEVELOPER,
        value="test-api-key"
    )


@pytest.mark.asyncio
async def test_transform_config_recursive_user_secret(mock_secrets_client):
    """Test that user secrets remain as tags during deploy phase."""
    # Create a config with a user secret
    config = {
        "user": {
            "password": UserSecret("${oc.env:USER_PASSWORD}")
        }
    }
    
    # Transform the config
    result = await transform_config_recursive(config, mock_secrets_client)
    
    # Verify the result
    assert "user" in result
    assert "password" in result["user"]
    
    # User secret should REMAIN as a UserSecret object
    assert isinstance(result["user"]["password"], UserSecret)
    assert result["user"]["password"].value == "${oc.env:USER_PASSWORD}"
    
    # Verify create_secret was NOT called for user secrets
    mock_secrets_client.create_secret.assert_not_called()


@pytest.mark.asyncio
async def test_transform_config_recursive_mixed_secrets(mock_secrets_client):
    """Test transforming a config with both developer and user secrets."""
    # Create a complex config with both types of secrets
    config = {
        "api": {
            "key": DeveloperSecret("dev-api-key"),
            "user_token": UserSecret("${oc.env:USER_TOKEN}")
        },
        "database": {
            "password": DeveloperSecret("dev-db-password"),
            "user_password": UserSecret()  # Empty user secret
        }
    }
    
    # Transform the config
    result = await transform_config_recursive(config, mock_secrets_client)
    
    # Verify the result
    # Developer secrets should be UUIDs
    assert isinstance(result["api"]["key"], str)
    assert "12345678-abcd-1234-efgh-dev-" in result["api"]["key"]
    
    assert isinstance(result["database"]["password"], str)
    assert "12345678-abcd-1234-efgh-dev-" in result["database"]["password"]
    
    # User secrets should remain as UserSecret objects
    assert isinstance(result["api"]["user_token"], UserSecret)
    assert result["api"]["user_token"].value == "${oc.env:USER_TOKEN}"
    
    assert isinstance(result["database"]["user_password"], UserSecret)
    assert result["database"]["user_password"].value is None
    
    # Verify create_secret was called only for developer secrets
    assert mock_secrets_client.create_secret.call_count == 2
    
    # Check the actual calls
    calls = mock_secrets_client.create_secret.call_args_list
    assert calls[0][1]["name"] in ["api.key", "database.password"]
    assert calls[0][1]["secret_type"] == SecretType.DEVELOPER
    assert calls[1][1]["name"] in ["api.key", "database.password"]
    assert calls[1][1]["secret_type"] == SecretType.DEVELOPER


@pytest.mark.asyncio
async def test_transform_recursive_nested_structure(mock_secrets_client):
    """Test transforming deeply nested config with secrets."""
    # Create a deeply nested config
    config = {
        "level1": {
            "level2": {
                "level3": {
                    "api_key": DeveloperSecret("nested-key"),
                    "user_key": UserSecret()
                }
            },
            "array": [
                {"secret": DeveloperSecret("array-item-1")},
                {"secret": UserSecret()}
            ]
        }
    }
    
    # Transform the config
    result = await transform_config_recursive(config, mock_secrets_client)
    
    # Verify the nested developer secret was transformed to UUID
    assert isinstance(result["level1"]["level2"]["level3"]["api_key"], str)
    assert "12345678-abcd-1234-efgh-dev-" in result["level1"]["level2"]["level3"]["api_key"]
    
    # Verify the nested user secret remained as a tag
    assert isinstance(result["level1"]["level2"]["level3"]["user_key"], UserSecret)
    
    # Verify array item developer secret was transformed
    assert isinstance(result["level1"]["array"][0]["secret"], str)
    assert "12345678-abcd-1234-efgh-dev-" in result["level1"]["array"][0]["secret"]
    
    # Verify array item user secret remained as a tag
    assert isinstance(result["level1"]["array"][1]["secret"], UserSecret)


@pytest.mark.asyncio
async def test_process_secrets_in_config(mock_secrets_client):
    """Test processing secrets in a full config string."""
    # Sample config with both types of secrets
    config_str = """
    api:
      key: !developer_secret dev-api-key
      token: !user_secret ${oc.env:USER_TOKEN}
    database:
      password: !developer_secret db-password
      user_password: !user_secret
    """
    
    # Process the config
    with patch("yaml.dump") as mock_dump:
        # Set up mock to return the processed YAML
        mock_dump.return_value = "processed yaml"
        
        result = await process_secrets_in_config(config_str, mock_secrets_client)
    
    # Verify the calls to transform_config_recursive (indirectly)
    assert mock_secrets_client.create_secret.call_count == 2  # Only dev secrets
    
    # Check that all calls were for developer secrets
    calls = mock_secrets_client.create_secret.call_args_list
    assert all(call[1]["secret_type"] == SecretType.DEVELOPER for call in calls)
    
    # Verify the result is the processed YAML
    assert result == "processed yaml"