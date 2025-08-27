"""Tests for SecretsClient API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp_agent.cli.core.constants import SecretType
from mcp_agent.cli.secrets.api_client import SecretsClient


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
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
        mock_instance.get.return_value = mock_response
        mock_instance.put.return_value = mock_response

        yield mock_instance


@pytest.fixture
def api_client():
    """Create a SecretsClient."""
    return SecretsClient(api_url="http://localhost:3000/api", api_key="test-token")


@pytest.mark.asyncio
async def test_create_developer_secret(api_client, mock_httpx_client):
    """Test creating a developer secret via the API."""
    # Create a developer secret
    handle = await api_client.create_secret(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="test-api-key",
    )

    # Check the returned handle is a string (UUID)
    assert handle == "mcpac_sc_12345678-abcd-1234-abcd-123456789abc"

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/create_secret"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"

    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.api_key"
    assert kwargs["json"]["value"] == "test-api-key"
    # Note: Secret type is handled locally, not sent to API


@pytest.mark.asyncio
async def test_create_user_secret(api_client, mock_httpx_client):
    """Test creating a user secret via the API."""
    # Create a user secret with a value
    handle = await api_client.create_secret(
        name="server.bedrock.user_access_key",
        secret_type=SecretType.USER,
        value="user-provided-value",
    )

    # Check the returned handle is a string (UUID)
    assert handle == "mcpac_sc_12345678-abcd-1234-abcd-123456789abc"

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/create_secret"

    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.user_access_key"
    assert kwargs["json"]["value"] == "user-provided-value"  # Value is required
    # Note: Secret type is handled locally, not sent to API


@pytest.mark.asyncio
async def test_create_secret_without_value(api_client):
    """Test creating any secret without a value raises ValueError."""
    # Create a secret without a value should raise ValueError for all types
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.api_key", secret_type=SecretType.DEVELOPER, value=None
        )

    # Empty string should also raise ValueError
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.user_key", secret_type=SecretType.USER, value=""
        )

    # Whitespace-only string should also raise ValueError
    with pytest.raises(ValueError, match="Secret .* requires a non-empty value"):
        await api_client.create_secret(
            name="server.bedrock.test_key", secret_type=SecretType.USER, value="   "
        )


@pytest.mark.asyncio
async def test_get_secret_value(api_client, mock_httpx_client):
    """Test getting a secret value via the API."""
    # Skip this test during development as the endpoint isn't implemented
    pytest.skip("API endpoint not fully implemented yet")

    # Configure mock response
    mock_httpx_client.post.return_value.json.return_value = {"value": "test-api-key"}

    # Get a secret value
    value = await api_client.get_secret_value("12345678-abcd-1234-efgh-123456789abc")

    # Check the returned value
    assert value == "test-api-key"

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/get_secret_value"

    # Check payload
    assert kwargs["json"]["secretId"] == "12345678-abcd-1234-efgh-123456789abc"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_set_secret_value(api_client, mock_httpx_client):
    """Test setting a secret value via the API."""
    # Skip this test during development as the endpoint isn't implemented
    pytest.skip("API endpoint not fully implemented yet")

    # Set a secret value
    await api_client.set_secret_value(
        "12345678-abcd-1234-efgh-123456789abc", "new-api-key"
    )

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/set_secret_value"

    # Check payload
    assert kwargs["json"]["secretId"] == "12345678-abcd-1234-efgh-123456789abc"
    assert kwargs["json"]["value"] == "new-api-key"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_list_secrets(api_client, mock_httpx_client):
    """Test listing secrets via the API."""
    # Configure mock response with standardized format
    secrets_list = [
        {
            "secretId": "12345678-abcd-1234-efgh-123456789abc",
            "name": "server.bedrock.api_key",
            "type": "dev",
        },
        {
            "secretId": "98765432-wxyz-9876-abcd-987654321def",
            "name": "server.bedrock.user_access_key",
            "type": "usr",
        },
    ]
    mock_httpx_client.post.return_value.json.return_value = {"secrets": secrets_list}

    # List secrets
    secrets = await api_client.list_secrets()

    # Check the returned list
    assert len(secrets) == 2
    assert secrets[0]["secretId"] == "12345678-abcd-1234-efgh-123456789abc"
    assert secrets[1]["secretId"] == "98765432-wxyz-9876-abcd-987654321def"
    # Verify type format matches expected values
    assert secrets[0]["type"] == "dev"
    assert secrets[1]["type"] == "usr"

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL
    assert args[0] == "http://localhost:3000/api/secrets/list"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_list_secrets_with_filter(api_client, mock_httpx_client):
    """Test listing secrets with a name filter."""
    # List secrets with filter
    await api_client.list_secrets(name_filter="bedrock")

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check payload includes the filter
    assert kwargs["json"]["nameFilter"] == "bedrock"


@pytest.mark.asyncio
async def test_delete_secret(api_client, mock_httpx_client):
    """Test deleting a secret via the API."""
    # Skip this test during development as the endpoint isn't implemented
    pytest.skip("API endpoint not fully implemented yet")

    # Delete a secret
    await api_client.delete_secret("12345678-abcd-1234-efgh-123456789abc")

    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args

    # Check URL
    assert args[0] == "http://localhost:3000/api/secrets/delete_secret"

    # Check payload
    assert kwargs["json"]["secretId"] == "12345678-abcd-1234-efgh-123456789abc"

    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_invalid_handle_format(api_client):
    """Test invalid handle format validation."""
    # Test with empty handle (should be rejected)
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.get_secret_value("")

    # Test with plain string that's not a UUID (should be rejected)
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.get_secret_value("not-a-uuid")

    # Test with almost-UUID but invalid format (should be rejected)
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.set_secret_value(
            "12345678-abcd-1234-INVALID-123456789abc", "new-value"
        )

    # Test with invalid prefix (should be rejected)
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.delete_secret(
            "wrong_prefix_12345678-abcd-1234-efgh-123456789abc"
        )


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
    # Skip this test during development as the endpoint isn't implemented
    pytest.skip("API endpoint not fully implemented yet")

    with patch("httpx.AsyncClient") as mock_client:
        # Configure the client to return an error response
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        # Create mock responses for different HTTP status codes
        not_found_response = MagicMock()
        not_found_response.status_code = 404
        not_found_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Secret not found", request=MagicMock(), response=not_found_response
        )

        forbidden_response = MagicMock()
        forbidden_response.status_code = 403
        forbidden_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=forbidden_response
        )

        # Test 404 Not Found response
        mock_instance.post.return_value = not_found_response
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await api_client.get_secret_value("12345678-abcd-1234-efgh-123456789abc")
        assert excinfo.value.response.status_code == 404

        # Test 403 Forbidden response
        mock_instance.post.return_value = forbidden_response
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await api_client.get_secret_value("12345678-abcd-1234-efgh-123456789abc")
        assert excinfo.value.response.status_code == 403
