"""Comprehensive tests for token verification functionality."""

import asyncio
import time
import pytest
from unittest.mock import Mock, AsyncMock
import httpx
from mcp_agent.config import MCPAuthorizationServerSettings
from mcp_agent.server.token_verifier import MCPAgentTokenVerifier


@pytest.mark.asyncio
async def test_fetch_introspection_endpoint_from_well_known():
    """Test fetching introspection endpoint from .well-known metadata."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to return metadata
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/oauth2/introspect",
        "response_types_supported": ["code"],
    }

    verifier._client.get = AsyncMock(return_value=mock_response)

    endpoint = await verifier._ensure_introspection_endpoint()

    assert endpoint == "https://auth.example.com/oauth2/introspect"
    assert (
        verifier._introspection_endpoint == "https://auth.example.com/oauth2/introspect"
    )

    # Verify it's cached - call again and it should return cached value
    endpoint2 = await verifier._ensure_introspection_endpoint()
    assert endpoint2 == endpoint

    # Verify only one HTTP call was made (cached on second call)
    assert verifier._client.get.call_count == 1

    await verifier.aclose()


@pytest.mark.asyncio
async def test_fetch_introspection_endpoint_with_path():
    """Test fetching introspection endpoint when issuer has a path component."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com/tenants/abc",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to return metadata
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "issuer": "https://auth.example.com/tenants/abc",
        "authorization_endpoint": "https://auth.example.com/tenants/abc/authorize",
        "token_endpoint": "https://auth.example.com/tenants/abc/token",
        "introspection_endpoint": "https://auth.example.com/tenants/abc/introspect",
        "response_types_supported": ["code"],
    }

    verifier._client.get = AsyncMock(return_value=mock_response)

    endpoint = await verifier._ensure_introspection_endpoint()

    assert endpoint == "https://auth.example.com/tenants/abc/introspect"

    # Verify the well-known URL was constructed correctly
    call_args = verifier._client.get.call_args[0]
    assert "/.well-known/oauth-authorization-server/tenants/abc" in call_args[0]

    await verifier.aclose()


@pytest.mark.asyncio
async def test_missing_issuer_url():
    """Test that authorization requires issuer_url to be configured."""
    # When authorization is enabled, issuer_url is required by validation
    # This test verifies that the config validation works correctly
    with pytest.raises(ValueError, match="issuer_url.*must be set"):
        MCPAuthorizationServerSettings(
            enabled=True,
            resource_server_url="https://api.example.com",
            expected_audiences=["https://api.example.com", "https://api.example.com/"],
        )


@pytest.mark.asyncio
async def test_well_known_endpoint_missing_introspection():
    """Test error when well-known metadata doesn't include introspection_endpoint."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to return metadata without introspection_endpoint
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "response_types_supported": ["code"],
        # Missing introspection_endpoint
    }

    verifier._client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(
        ValueError, match="does not advertise an introspection endpoint"
    ):
        await verifier._ensure_introspection_endpoint()

    await verifier.aclose()


@pytest.mark.asyncio
async def test_well_known_endpoint_http_error():
    """Test error handling when fetching well-known metadata fails."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to raise an error
    verifier._client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))

    with pytest.raises(ValueError, match="Failed to fetch introspection endpoint"):
        await verifier._ensure_introspection_endpoint()

    await verifier.aclose()


@pytest.mark.asyncio
async def test_well_known_endpoint_404_error():
    """Test error handling when well-known endpoint returns 404."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to raise 404
    verifier._client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock(status_code=404)
        )
    )

    with pytest.raises(ValueError, match="Failed to fetch introspection endpoint"):
        await verifier._ensure_introspection_endpoint()

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_without_client_auth():
    """Test token introspection without client authentication."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock successful introspection response
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is not None
    assert token.subject == "user123"

    # Verify no auth was used
    call_kwargs = verifier._client.post.call_args[1]
    assert call_kwargs.get("auth") is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_with_client_auth():
    """Test token introspection with client authentication."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        client_id="client123",
        client_secret="secret456",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock successful introspection response
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is not None

    # Verify auth was used
    call_kwargs = verifier._client.post.call_args[1]
    auth = call_kwargs.get("auth")
    assert auth is not None
    assert isinstance(auth, httpx.BasicAuth)

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_http_error():
    """Test handling of HTTP errors during introspection."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(side_effect=httpx.HTTPError("Network error"))

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_non_200_response():
    """Test handling of non-200 responses from introspection endpoint."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock 401 response
    introspect_response = Mock()
    introspect_response.status_code = 401

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_invalid_json():
    """Test handling of invalid JSON response from introspection endpoint."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock response with invalid JSON
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.side_effect = ValueError("Invalid JSON")

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_inactive_token():
    """Test handling of inactive token."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock inactive token response
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": False,
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_issuer_mismatch():
    """Test handling of issuer mismatch."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock response with wrong issuer
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://malicious.example.com",  # Wrong issuer
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_missing_required_scopes():
    """Test handling of missing required scopes."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        required_scopes=["read", "write"],
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock response with insufficient scopes
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "scope": "read",  # Missing 'write' scope
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_introspect_with_ttl_limit():
    """Test token cache TTL limiting."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        token_cache_ttl_seconds=60,
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock response with long expiration
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,  # Far in the future
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is not None
    # The expires_at should be capped by TTL
    max_expected_expiry = time.time() + 60 + 5  # TTL + small buffer
    assert token.expires_at <= max_expected_expiry

    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_caching():
    """Test that verify_token properly caches tokens."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock successful introspection response
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    # First call should hit the introspection endpoint
    token1 = await verifier.verify_token("test_token")
    assert token1 is not None
    assert verifier._client.post.call_count == 1

    # Second call should use cache
    token2 = await verifier.verify_token("test_token")
    assert token2 is not None
    assert token2 is token1  # Same object from cache
    assert verifier._client.post.call_count == 1  # No additional call

    await verifier.aclose()


@pytest.mark.asyncio
async def test_verify_token_cache_removal_on_failure():
    """Test that failed verification removes token from cache."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)

    # First call: valid token
    introspect_response1 = Mock()
    introspect_response1.status_code = 200
    introspect_response1.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",
    }

    verifier._client.post = AsyncMock(return_value=introspect_response1)

    token1 = await verifier.verify_token("test_token")
    assert token1 is not None

    # Second call: token becomes inactive
    introspect_response2 = Mock()
    introspect_response2.status_code = 200
    introspect_response2.json.return_value = {
        "active": False,
    }

    verifier._client.post = AsyncMock(return_value=introspect_response2)

    # Clear cache to force re-verification
    verifier._cache.clear()

    token2 = await verifier.verify_token("test_token")
    assert token2 is None

    # Verify token was removed from cache
    assert "test_token" not in verifier._cache

    await verifier.aclose()


@pytest.mark.asyncio
async def test_context_manager():
    """Test using verifier as async context manager."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    async with MCPAgentTokenVerifier(settings) as verifier:
        assert verifier is not None
        assert verifier._client is not None


@pytest.mark.asyncio
async def test_concurrent_metadata_fetch():
    """Test that concurrent calls to fetch metadata only make one request."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client to return metadata
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)  # Simulate network delay
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "introspection_endpoint": "https://auth.example.com/oauth2/introspect",
            "response_types_supported": ["code"],
        }
        return mock_response

    verifier._client.get = mock_get

    # Make multiple concurrent calls
    results = await asyncio.gather(
        verifier._ensure_introspection_endpoint(),
        verifier._ensure_introspection_endpoint(),
        verifier._ensure_introspection_endpoint(),
    )

    # All should return the same endpoint
    assert all(r == "https://auth.example.com/oauth2/introspect" for r in results)

    # But only one HTTP call should have been made (due to locking)
    assert call_count == 1

    await verifier.aclose()


@pytest.mark.asyncio
async def test_audience_extraction():
    """Test audience extraction from various token payloads."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api.example.com/"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Test string audience
    audiences = verifier._extract_audiences({"aud": "https://api.example.com"})
    assert "https://api.example.com" in audiences

    # Test array audience
    audiences = verifier._extract_audiences(
        {"aud": ["https://api1.example.com", "https://api2.example.com"]}
    )
    assert "https://api1.example.com" in audiences
    assert "https://api2.example.com" in audiences

    # Test resource claim
    audiences = verifier._extract_audiences({"resource": "https://api.example.com"})
    assert "https://api.example.com" in audiences

    # Test combined aud and resource
    audiences = verifier._extract_audiences(
        {"aud": "https://api1.example.com", "resource": "https://api2.example.com"}
    )
    assert "https://api1.example.com" in audiences
    assert "https://api2.example.com" in audiences

    await verifier.aclose()


@pytest.mark.asyncio
async def test_audience_validation():
    """Test audience validation logic."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://api2.example.com"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Valid - exact match
    assert verifier._validate_audiences(["https://api.example.com"]) is True

    # Valid - one of multiple
    assert verifier._validate_audiences(["https://api2.example.com"]) is True

    # Valid - multiple with one match
    assert (
        verifier._validate_audiences(["https://api.example.com", "https://other.com"])
        is True
    )

    # Invalid - no match
    assert verifier._validate_audiences(["https://malicious.example.com"]) is False

    # Invalid - empty
    assert verifier._validate_audiences([]) is False

    await verifier.aclose()


@pytest.mark.asyncio
async def test_audience_validation_failure_through_introspect():
    """Test audience validation failure during token introspection."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://expected-api.example.com"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock well-known metadata
    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    # Mock introspection response with wrong audience
    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://wrong-api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    # Should return None due to audience mismatch
    assert token is None

    await verifier.aclose()


@pytest.mark.asyncio
async def test_issuer_comparison_with_trailing_slash_from_token():
    """Test that issuer comparison works when token has trailing slash.

    When config is loaded/dumped with mode='json', AnyHttpUrl fields may gain
    trailing slashes. This test ensures the issuer comparison in token_verifier.py:158
    handles this correctly.
    """
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com"],
    )

    # Dump with mode="json" and reload to simulate config loading (with trailing slashes)
    dumped = settings.model_dump(mode="json")
    reloaded_settings = MCPAuthorizationServerSettings(**dumped)

    verifier = MCPAgentTokenVerifier(reloaded_settings)

    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com/",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com/",  # trailing slash
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is not None
    assert token.subject == "user123"

    await verifier.aclose()


@pytest.mark.asyncio
async def test_issuer_comparison_config_trailing_slash_token_without():
    """Test issuer comparison when config has trailing slash but token doesn't."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com"],
    )

    dumped = settings.model_dump(mode="json")
    reloaded_settings = MCPAuthorizationServerSettings(**dumped)

    verifier = MCPAgentTokenVerifier(reloaded_settings)

    metadata_response = Mock()
    metadata_response.status_code = 200
    metadata_response.json.return_value = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "introspection_endpoint": "https://auth.example.com/introspect",
        "response_types_supported": ["code"],
    }

    introspect_response = Mock()
    introspect_response.status_code = 200
    introspect_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 9999999999,
        "iss": "https://auth.example.com",  # No trailing slash
    }

    verifier._client.get = AsyncMock(return_value=metadata_response)
    verifier._client.post = AsyncMock(return_value=introspect_response)

    token = await verifier._introspect("test_token")

    assert token is not None
    assert token.subject == "user123"

    await verifier.aclose()
