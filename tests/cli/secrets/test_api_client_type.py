"""Tests for the type field in the SecretsClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_agent.cli.core.constants import SecretType
from mcp_agent.cli.secrets.api_client import SecretsClient


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock_client:
        # Create a response mock
        response_mock = MagicMock()
        response_mock.json.return_value = {
            "secret": {"secretId": "mcpac_sc_12345678-abcd-1234-abcd-123456789abc"}
        }
        response_mock.raise_for_status = AsyncMock()

        # Configure the client's post method
        client_instance = MagicMock()
        client_instance.post = AsyncMock(return_value=response_mock)

        # Return the mocked client factory
        mock_client.return_value.__aenter__.return_value = client_instance
        yield mock_client


@pytest.mark.asyncio
async def test_create_secret_sends_correct_type_for_developer_secret(mock_httpx_client):
    """Test that create_secret sends the correct type for developer secrets."""
    # Arrange
    client = SecretsClient(api_url="http://test.com/api", api_key="test-token")

    # Act
    await client.create_secret(
        name="test-secret", secret_type=SecretType.DEVELOPER, value="test-value"
    )

    # Assert
    # Get the client instance
    client_instance = mock_httpx_client.return_value.__aenter__.return_value

    # Check that post was called with the correct type
    client_instance.post.assert_called_once()
    post_args = client_instance.post.call_args[0]
    post_kwargs = client_instance.post.call_args[1]

    # Verify the URL
    assert post_args[0] == "http://test.com/api/secrets/create_secret"

    # Verify the payload contains the correct type
    assert post_kwargs["json"]["type"] == "dev"
    assert post_kwargs["json"]["type"] == SecretType.DEVELOPER.value


@pytest.mark.asyncio
async def test_create_secret_sends_correct_type_for_user_secret(mock_httpx_client):
    """Test that create_secret sends the correct type for user secrets."""
    # Arrange
    client = SecretsClient(api_url="http://test.com/api", api_key="test-token")

    # Act
    await client.create_secret(
        name="test-secret",
        secret_type=SecretType.USER,
        value="test-user-secret-value",  # Non-empty value for user secrets
    )

    # Assert
    client_instance = mock_httpx_client.return_value.__aenter__.return_value
    client_instance.post.assert_called_once()
    post_kwargs = client_instance.post.call_args[1]

    # Verify the type is correct
    assert post_kwargs["json"]["type"] == "usr"
    assert post_kwargs["json"]["type"] == SecretType.USER.value
