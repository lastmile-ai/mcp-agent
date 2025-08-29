"""Tests for SecretsClient API client with focus on deploy phase functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp_agent.cli.core.constants import SecretType
from mcp_agent.cli.secrets.api_client import SecretsClient

from ..fixtures.test_constants import (
    BEDROCK_API_KEY_UUID,
    DATABASE_PASSWORD_UUID,
    TEST_SECRET_UUID,
)

# FIXTURES - Streamlined to focus on deploy scenario


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
    with patch("httpx.AsyncClient") as mock_client:
        # Configure the mock client
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        # Configure the mock response with the proper prefixed UUID from constants
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "secret": {"secretId": TEST_SECRET_UUID},
            "success": True,
        }
        # API should return the production-format prefixed UUID
        mock_instance.post.return_value = mock_response

        yield mock_instance


@pytest.fixture
def api_client():
    """Create a SecretsClient."""
    return SecretsClient(api_url="http://localhost:3000/api", api_key="test-token")


# DEVELOPER SECRET TESTS - Critical for deploy phase


@pytest.mark.asyncio
async def test_create_developer_secret(api_client, mock_httpx_client):
    """Test creating a developer secret via the API."""
    # Create a developer secret
    handle = await api_client.create_secret(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="test-api-key",
    )

    # Check the returned handle matches our constant
    assert handle == TEST_SECRET_UUID

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL
    assert args[0] == "http://localhost:3000/api/secrets/create_secret"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"

    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.api_key"
    assert kwargs["json"]["value"] == "test-api-key"
    assert kwargs["json"]["type"] == "dev"


@pytest.mark.asyncio
async def test_create_secret_sends_correct_type(api_client, mock_httpx_client):
    """Test that create_secret sends the correct type field for developer secrets."""
    # Create developer secret
    await api_client.create_secret(
        name="server.api_key", secret_type=SecretType.DEVELOPER, value="test-value"
    )

    # Verify type in API call
    args, kwargs = mock_httpx_client.post.call_args
    assert kwargs["json"]["type"] == "dev"
    assert kwargs["json"]["type"] == SecretType.DEVELOPER.value


# VALUE VALIDATION TESTS - Ensure proper validation


@pytest.mark.asyncio
async def test_create_secret_without_value(api_client):
    """Test creating any secret without a value raises ValueError."""
    # Create a secret without a value should raise ValueError
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.api_key", secret_type=SecretType.DEVELOPER, value=None
        )

    # Empty string should also raise ValueError
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.test_key", secret_type=SecretType.DEVELOPER, value=""
        )

    # Whitespace-only string should also raise ValueError
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.test_key",
            secret_type=SecretType.DEVELOPER,
            value="   ",
        )


# ERROR HANDLING TESTS - Critical for robustness


@pytest.mark.asyncio
async def test_api_connectivity_failure(api_client):
    """Test handling of API connectivity failures."""
    with patch("httpx.AsyncClient") as mock_client:
        # Configure the client to raise an exception (connection error)
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.side_effect = httpx.ConnectError("Failed to connect to API")

        # Test handling of connectivity failure during create_secret
        with pytest.raises(httpx.ConnectError):
            await api_client.create_secret(
                name="test.key", secret_type=SecretType.DEVELOPER, value="test-value"
            )


@pytest.mark.asyncio
async def test_http_error_handling(api_client):
    """Test handling of HTTP errors from the API."""
    with patch("httpx.AsyncClient") as mock_client:
        # Configure the client to return a 400 error
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        # Create a mock response with a 400 status code
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=MagicMock(status_code=400, text="Invalid request"),
        )
        mock_instance.post.return_value = mock_response

        # Test handling of HTTP error during create_secret
        with pytest.raises(httpx.HTTPStatusError):
            await api_client.create_secret(
                name="test.key", secret_type=SecretType.DEVELOPER, value="test-value"
            )


# REAL WORLD EXAMPLE TESTS - Based on CLAUDE.md


@pytest.mark.asyncio
async def test_deploy_phase_api_usage(api_client, mock_httpx_client):
    """Test API usage during deploy phase as described in CLAUDE.md."""
    # Configure mock to return proper production-format UUIDs for each call
    response_seq = [
        {
            "secret": {"secretId": BEDROCK_API_KEY_UUID},
            "success": True,
        },  # API returns standardized UUIDs
        {
            "secret": {"secretId": DATABASE_PASSWORD_UUID},
            "success": True,
        },  # API returns standardized UUIDs
    ]
    mock_httpx_client.post.side_effect = [
        MagicMock(raise_for_status=MagicMock(), json=MagicMock(return_value=response))
        for response in response_seq
    ]

    # Create developer secrets as would happen in deploy phase
    bedrock_handle = await api_client.create_secret(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="dev-bedrock-key-from-env",  # Value from BEDROCK_KEY env var
    )

    db_handle = await api_client.create_secret(
        name="database.password",
        secret_type=SecretType.DEVELOPER,
        value="prompted-db-password",  # Value from prompt
    )

    # Verify returned handles match our constants
    assert bedrock_handle == BEDROCK_API_KEY_UUID
    assert db_handle == DATABASE_PASSWORD_UUID

    # Verify API calls
    assert mock_httpx_client.post.call_count == 2

    # Verify first call (bedrock key)
    _, kwargs1 = mock_httpx_client.post.call_args_list[0]
    assert kwargs1["json"]["name"] == "server.bedrock.api_key"
    assert kwargs1["json"]["value"] == "dev-bedrock-key-from-env"
    assert kwargs1["json"]["type"] == "dev"

    # Verify second call (db password)
    _, kwargs2 = mock_httpx_client.post.call_args_list[1]
    assert kwargs2["json"]["name"] == "database.password"
    assert kwargs2["json"]["value"] == "prompted-db-password"
    assert kwargs2["json"]["type"] == "dev"
