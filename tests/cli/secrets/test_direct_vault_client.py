"""Tests for DirectVaultSecretsApiClient."""

import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_agent_cloud.secrets.direct_vault_client import DirectVaultSecretsApiClient
from mcp_agent_cloud.secrets.constants import SecretType


@pytest.fixture
def mock_vault_client():
    """Create a mock Vault client."""
    with patch("hvac.Client") as mock_client:
        # Configure the mock client
        mock_instance = mock_client.return_value
        mock_instance.secrets.kv.v2.create_or_update_secret = MagicMock()
        mock_instance.secrets.kv.v2.read_secret_version = MagicMock()
        
        yield mock_instance


@pytest.fixture
def direct_vault_client(mock_vault_client):
    """Create a DirectVaultSecretsApiClient with a mock Vault client."""
    return DirectVaultSecretsApiClient(
        vault_addr="http://localhost:8200",
        vault_token="mock-token"
    )


@pytest.mark.asyncio
async def test_create_developer_secret(direct_vault_client, mock_vault_client):
    """Test creating a developer secret."""
    # Setup mock to return a predictable UUID
    test_uuid = "12345678-1234-5678-1234-567812345678"
    with patch("uuid.uuid4", return_value=uuid.UUID(test_uuid)):
        # Create a developer secret
        handle = await direct_vault_client.create_secret(
            name="server.bedrock.api_key",
            type_=SecretType.DEVELOPER,
            value="test-api-key"
        )
        
        # Check the handle format
        assert handle == f"{direct_vault_client.DEV_HANDLE_PREFIX}{test_uuid}"
        
        # Verify Vault client was called correctly
        mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
        args, kwargs = mock_vault_client.secrets.kv.v2.create_or_update_secret.call_args
        
        # Check path and mount point
        assert kwargs["mount_point"] == "secret"
        assert kwargs["path"].startswith(f"{direct_vault_client.VAULT_SECRETS_PATH}/{handle}")
        
        # Check secret data
        secret_data = kwargs["secret"]
        assert secret_data["name"] == "server.bedrock.api_key"
        assert secret_data["type"] == "developer"
        assert secret_data["value"] == "test-api-key"


@pytest.mark.asyncio
async def test_create_user_secret(direct_vault_client, mock_vault_client):
    """Test creating a user secret."""
    # Setup mock to return a predictable UUID
    test_uuid = "12345678-1234-5678-1234-567812345678"
    with patch("uuid.uuid4", return_value=uuid.UUID(test_uuid)):
        # Create a user secret (no value provided)
        handle = await direct_vault_client.create_secret(
            name="server.bedrock.user_access_key",
            type_=SecretType.USER
        )
        
        # Check the handle format
        assert handle == f"{direct_vault_client.USR_HANDLE_PREFIX}{test_uuid}"
        
        # Verify Vault client was called correctly
        mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
        args, kwargs = mock_vault_client.secrets.kv.v2.create_or_update_secret.call_args
        
        # Check path and mount point
        assert kwargs["mount_point"] == "secret"
        assert kwargs["path"].startswith(f"{direct_vault_client.VAULT_SECRETS_PATH}/{handle}")
        
        # Check secret data
        secret_data = kwargs["secret"]
        assert secret_data["name"] == "server.bedrock.user_access_key"
        assert secret_data["type"] == "user"
        assert "value" not in secret_data  # No value for user secret