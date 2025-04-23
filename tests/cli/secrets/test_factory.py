"""Tests for the secrets factory."""

import pytest
from unittest.mock import patch, MagicMock

from mcp_agent_cloud.secrets.factory import get_secrets_client
from mcp_agent_cloud.secrets.constants import SecretsMode
from mcp_agent_cloud.secrets.direct_vault_client import DirectVaultSecretsApiClient
from mcp_agent_cloud.config.settings import settings


def test_get_direct_vault_client():
    """Test getting a DirectVaultSecretsApiClient."""
    # Mock settings so they don't interfere with the test
    with patch.object(settings, 'VAULT_ADDR', ''), \
         patch.object(settings, 'VAULT_TOKEN', ''):
        client = get_secrets_client(
            mode=SecretsMode.DIRECT_VAULT,
            vault_addr="http://test-vault:8200",
            vault_token="test-token"
        )
        
        assert isinstance(client, DirectVaultSecretsApiClient)
        assert client.vault_client.url == "http://test-vault:8200"
        assert client.vault_client.token == "test-token"


@patch("mcp_agent_cloud.secrets.factory._http_client_available", True)
@patch("mcp_agent_cloud.secrets.factory.HttpSecretsApiClient")
def test_get_http_client(mock_http_client):
    """Test getting an HttpSecretsApiClient."""
    # Mock the HttpSecretsApiClient constructor
    mock_instance = MagicMock()
    mock_http_client.return_value = mock_instance
    
    # Mock settings so they don't interfere with the test
    with patch.object(settings, 'SECRETS_API_URL', ''), \
         patch.object(settings, 'SECRETS_API_TOKEN', ''):
        client = get_secrets_client(
            mode=SecretsMode.API,
            api_url="http://test-api:3000/api/v1",
            api_token="test-token"
        )
        
        # Should have created an HttpSecretsApiClient
        mock_http_client.assert_called_once_with(
            api_url="http://test-api:3000/api/v1",
            api_token="test-token"
        )
        
        # Should have returned the mock instance
        assert client == mock_instance


@patch("mcp_agent_cloud.secrets.factory._http_client_available", False)
def test_get_http_client_not_available():
    """Test that get_secrets_client raises ImportError when HttpSecretsApiClient is not available."""
    with pytest.raises(ImportError, match="HTTP client is not available"):
        get_secrets_client(
            mode=SecretsMode.API,
            api_url="http://test-api:3000/api/v1",
            api_token="test-token"
        )


def test_get_unknown_mode():
    """Test that get_secrets_client raises ValueError for unknown mode."""
    with pytest.raises(ValueError, match="Unknown secrets mode"):
        get_secrets_client(
            mode="unknown_mode"
        )