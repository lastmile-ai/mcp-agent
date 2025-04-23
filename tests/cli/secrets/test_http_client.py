"""Tests for HttpSecretsApiClient."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_agent_cloud.secrets.http_client import HttpSecretsApiClient
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
def http_client():
    """Create an HttpSecretsApiClient."""
    return HttpSecretsApiClient(
        api_url="http://localhost:3000/api/v1",
        api_token="test-token"
    )


@pytest.mark.asyncio
async def test_create_developer_secret(http_client, mock_httpx_client):
    """Test creating a developer secret via the API."""
    # Create a developer secret
    handle = await http_client.create_secret(
        name="server.bedrock.api_key",
        type_=SecretType.DEVELOPER,
        value="test-api-key"
    )
    
    # Check the returned handle
    assert handle == "mcpac_dev_12345"
    
    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args
    
    # Check URL
    assert args[0] == "http://localhost:3000/api/v1/secrets"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    
    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.api_key"
    assert kwargs["json"]["type"] == "developer"
    assert kwargs["json"]["value"] == "test-api-key"


@pytest.mark.asyncio
async def test_create_user_secret(http_client, mock_httpx_client):
    """Test creating a user secret via the API."""
    # Create a user secret (no value provided)
    handle = await http_client.create_secret(
        name="server.bedrock.user_access_key",
        type_=SecretType.USER
    )
    
    # Check the returned handle
    assert handle == "mcpac_dev_12345"
    
    # Verify API was called correctly
    mock_httpx_client.post.assert_called_once()
    args, kwargs = mock_httpx_client.post.call_args
    
    # Check URL
    assert args[0] == "http://localhost:3000/api/v1/secrets"
    
    # Check payload
    assert kwargs["json"]["name"] == "server.bedrock.user_access_key"
    assert kwargs["json"]["type"] == "user"
    assert "value" not in kwargs["json"]  # No value for user secret


@pytest.mark.asyncio
async def test_get_secret_value(http_client, mock_httpx_client):
    """Test getting a secret value via the API."""
    # Configure mock response
    mock_httpx_client.get.return_value.json.return_value = {"value": "test-api-key"}
    
    # Get a secret value
    value = await http_client.get_secret_value("mcpac_dev_12345")
    
    # Check the returned value
    assert value == "test-api-key"
    
    # Verify API was called correctly
    mock_httpx_client.get.assert_called_once()
    args, kwargs = mock_httpx_client.get.call_args
    
    # Check URL
    assert args[0] == "http://localhost:3000/api/v1/secrets/mcpac_dev_12345/value"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_set_secret_value(http_client, mock_httpx_client):
    """Test setting a secret value via the API."""
    # Set a secret value
    await http_client.set_secret_value("mcpac_dev_12345", "new-api-key")
    
    # Verify API was called correctly
    mock_httpx_client.put.assert_called_once()
    args, kwargs = mock_httpx_client.put.call_args
    
    # Check URL
    assert args[0] == "http://localhost:3000/api/v1/secrets/mcpac_dev_12345/value"
    
    # Check payload
    assert kwargs["json"]["value"] == "new-api-key"
    
    # Check headers
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"