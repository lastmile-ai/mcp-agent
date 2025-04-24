"""Tests for SecretsClient API client."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.constants import SecretType


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
        mock_response.json.return_value = {"id": "mcpac_dev_12345", "success": True}
        mock_instance.post.return_value = mock_response
        mock_instance.get.return_value = mock_response
        mock_instance.put.return_value = mock_response
        
        yield mock_instance


@pytest.fixture
def api_client():
    """Create a SecretsClient."""
    return SecretsClient(
        api_url="http://localhost:3000/api",
        api_token="test-token"
    )


@pytest.mark.asyncio
async def test_create_developer_secret(api_client, mock_httpx_client):
    """Test creating a developer secret via the API."""
    # Create a developer secret
    handle = await api_client.create_secret(
        name="server.bedrock.api_key",
        secret_type=SecretType.DEVELOPER,
        value="test-api-key"
    )
    
    # Check the returned handle
    assert handle == "mcpac_dev_12345"
    
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
    assert kwargs["json"]["type"] == "developer"
    assert kwargs["json"]["value"] == "test-api-key"


@pytest.mark.asyncio
async def test_create_user_secret(api_client, mock_httpx_client):
    """Test creating a user secret via the API."""
    # Create a user secret (no value provided)
    handle = await api_client.create_secret(
        name="server.bedrock.user_access_key",
        secret_type=SecretType.USER
    )
    
    # Check the returned handle
    assert handle == "mcpac_dev_12345"
    
    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args
    
    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/create_secret"
    
    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.user_access_key"
    assert kwargs["json"]["type"] == "user"
    assert "value" not in kwargs["json"]  # No value for user secret


@pytest.mark.asyncio
async def test_create_developer_secret_without_value(api_client):
    """Test creating a developer secret without a value raises ValueError."""
    # Create a developer secret without a value should raise ValueError
    with pytest.raises(ValueError, match="Developer secret .* requires a value"):
        await api_client.create_secret(
            name="server.bedrock.api_key",
            secret_type=SecretType.DEVELOPER,
            value=None
        )


@pytest.mark.asyncio
async def test_get_secret_value(api_client, mock_httpx_client):
    """Test getting a secret value via the API."""
    # Configure mock response
    mock_httpx_client.post.return_value.json.return_value = {"value": "test-api-key"}
    
    # Get a secret value
    value = await api_client.get_secret_value("mcpac_dev_12345")
    
    # Check the returned value
    assert value == "test-api-key"
    
    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args
    
    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/get_secret_value"
    
    # Check payload
    assert kwargs["json"]["secretId"] == "mcpac_dev_12345"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_set_secret_value(api_client, mock_httpx_client):
    """Test setting a secret value via the API."""
    # Set a secret value
    await api_client.set_secret_value("mcpac_dev_12345", "new-api-key")
    
    # Verify API was called correctly
    mock_httpx_client.put.assert_called_once()
    args, kwargs = mock_httpx_client.put.call_args
    
    # Check URL - updated to match new API endpoints
    assert args[0] == "http://localhost:3000/api/secrets/set_secret_value"
    
    # Check payload
    assert kwargs["json"]["secretId"] == "mcpac_dev_12345"
    assert kwargs["json"]["value"] == "new-api-key"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_list_secrets(api_client, mock_httpx_client):
    """Test listing secrets via the API."""
    # Configure mock response
    secrets_list = [
        {"id": "mcpac_dev_12345", "name": "server.bedrock.api_key", "type": "developer"},
        {"id": "mcpac_usr_67890", "name": "server.bedrock.user_access_key", "type": "user"}
    ]
    mock_httpx_client.post.return_value.json.return_value = {"secrets": secrets_list}
    
    # List secrets
    secrets = await api_client.list_secrets()
    
    # Check the returned list
    assert len(secrets) == 2
    assert secrets[0]["id"] == "mcpac_dev_12345"
    assert secrets[1]["id"] == "mcpac_usr_67890"
    
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
    # Delete a secret
    await api_client.delete_secret("mcpac_dev_12345")
    
    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args
    
    # Check URL
    assert args[0] == "http://localhost:3000/api/secrets/delete_secret"
    
    # Check payload
    assert kwargs["json"]["secretId"] == "mcpac_dev_12345"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_invalid_handle_format(api_client):
    """Test invalid handle format validation."""
    # Test with invalid handle format
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.get_secret_value("invalid_handle")
    
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.set_secret_value("invalid_handle", "new-value")
    
    with pytest.raises(ValueError, match="Invalid handle format"):
        await api_client.delete_secret("invalid_handle")