"""Test the API key parameter renaming."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import SecretType
from mcp_agent.cli.secrets.api_client import SecretsClient


def test_api_client_init_uses_api_key():
    """Test that SecretsClient initializes correctly with api_key parameter."""
    # Create a client with the new api_key parameter
    client = SecretsClient(api_url="http://test-url", api_key="test-api-key")

    # Verify the api_key was stored correctly
    assert client.api_key == "test-api-key"
    assert hasattr(client, "api_key")
    assert not hasattr(client, "api_token")


@pytest.mark.asyncio
async def test_api_client_request_uses_api_key():
    """Test that SecretsClient uses api_key in headers for requests."""
    with patch("httpx.AsyncClient") as mock_client:
        # Configure the mock client
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        # Configure the mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "secret": {"secretId": "mcpac_sc_12345678-abcd-1234-abcd-123456789abc"},
            "success": True,
        }
        mock_instance.post.return_value = mock_response

        # Create the client with api_key
        client = SecretsClient(api_url="http://test-url", api_key="test-api-key")

        # Call a method that makes an API request
        await client.create_secret(
            name="test.secret", secret_type=SecretType.DEVELOPER, value="test-value"
        )

        # Verify the api_key was used in the Authorization header
        mock_instance.post.assert_called_once()
        args, kwargs = mock_instance.post.call_args

        # Check headers contains the api_key
        assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"


def test_settings_api_key():
    """Test that the config.settings module uses API_KEY."""
    # Verify settings has API_KEY attribute
    assert hasattr(settings, "API_KEY")
    # API_TOKEN should not exist anymore
    assert not hasattr(settings, "SECRETS_API_TOKEN")
