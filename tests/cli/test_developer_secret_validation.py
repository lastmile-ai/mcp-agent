"""Tests for developer secret validation."""

import pytest
from unittest.mock import AsyncMock

from mcp_agent_cloud.secrets.processor import transform_config_recursive
from mcp_agent_cloud.secrets.yaml_tags import DeveloperSecret
from mcp_agent_cloud.core.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return UUIDs
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a deterministic UUID-like string based on name
        return f"{name.replace('.', '-')}-uuid"
    
    client.create_secret.side_effect = mock_create_secret
    return client


@pytest.mark.asyncio
async def test_developer_secret_with_empty_value(mock_secrets_client):
    """Test that developer secrets with empty values raise an error."""
    # Create a developer secret with empty string
    dev_secret = DeveloperSecret("")
    
    # Attempt to transform the secret
    with pytest.raises(ValueError, match="Developer secret at .* has no value.*non-interactive is set"):
        await transform_config_recursive(
            dev_secret,
            mock_secrets_client,
            "server.api_key",
            non_interactive=True
        )


@pytest.mark.asyncio
async def test_developer_secret_with_none_value(mock_secrets_client):
    """Test that developer secrets with None values raise an error."""
    # Create a developer secret with None value
    dev_secret = DeveloperSecret(None)
    
    # Attempt to transform the secret
    with pytest.raises(ValueError, match="Developer secret at .* has no value.*non-interactive is set"):
        await transform_config_recursive(
            dev_secret,
            mock_secrets_client,
            "server.api_key",
            non_interactive=True
        )


@pytest.mark.asyncio
async def test_developer_secret_with_env_var_not_found(mock_secrets_client, monkeypatch):
    """Test that developer secrets with missing env vars raise an error."""
    # Ensure env var doesn't exist
    monkeypatch.delenv("NON_EXISTENT_ENV_VAR", raising=False)
    
    # Create a developer secret with env var reference
    dev_secret = DeveloperSecret("${oc.env:NON_EXISTENT_ENV_VAR}")
    
    # Attempt to transform the secret
    with pytest.raises(ValueError, match="Developer secret at .* has no value.*non-interactive is set"):
        await transform_config_recursive(
            dev_secret,
            mock_secrets_client,
            "server.api_key",
            non_interactive=True
        )