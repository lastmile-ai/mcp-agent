"""Test audience validation functionality for RFC 9068 compliance."""

import pytest
from unittest.mock import Mock, AsyncMock
import httpx
from mcp_agent.config import MCPAuthorizationServerSettings
from mcp_agent.server.token_verifier import MCPAgentTokenVerifier
from mcp_agent.oauth.access_token import MCPAccessToken, _extract_all_audiences


@pytest.mark.asyncio
async def test_audience_validation_success():
    """Test successful audience validation with matching audiences."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "api.example.com"],
    )

    # Mock successful introspection response with valid audience
    payload = {
        "active": True,
        "aud": ["https://api.example.com", "other.example.com"],
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }

    token = MCPAccessToken.from_introspection("test_token", payload)
    assert token.validate_audience(settings.expected_audiences) is True


@pytest.mark.asyncio
async def test_audience_validation_failure():
    """Test audience validation failure with non-matching audiences."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com"],
    )

    payload = {
        "active": True,
        "aud": ["https://malicious.example.com"],  # Wrong audience
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }

    token = MCPAccessToken.from_introspection("test_token", payload)
    assert token.validate_audience(settings.expected_audiences) is False


@pytest.mark.asyncio
async def test_resource_claim_audience_validation():
    """Test audience validation using OAuth 2.0 resource indicators."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com"],
    )

    # Token with resource claim instead of aud claim
    payload = {
        "active": True,
        "resource": "https://api.example.com",  # OAuth 2.0 resource indicator
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }

    token = MCPAccessToken.from_introspection("test_token", payload)
    assert token.validate_audience(settings.expected_audiences) is True


@pytest.mark.asyncio
async def test_multiple_audiences_extraction():
    """Test extraction of multiple audiences from both aud and resource claims."""
    payload = {
        "aud": ["https://api1.example.com", "https://api2.example.com"],
        "resource": "https://api3.example.com",
    }

    audiences = _extract_all_audiences(payload)
    expected = {
        "https://api1.example.com",
        "https://api2.example.com",
        "https://api3.example.com",
    }
    assert set(audiences) == expected


@pytest.mark.asyncio
async def test_audience_extraction_string_values():
    """Test extraction when aud and resource are strings rather than arrays."""
    payload = {
        "aud": "https://api1.example.com",
        "resource": "https://api2.example.com",
    }

    audiences = _extract_all_audiences(payload)
    expected = {"https://api1.example.com", "https://api2.example.com"}
    assert set(audiences) == expected


@pytest.mark.asyncio
async def test_empty_audience_validation():
    """Test validation fails when no audiences are present."""
    payload = {
        "active": True,
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
        # No aud or resource claims
    }

    token = MCPAccessToken.from_introspection("test_token", payload)
    assert token.validate_audience(["https://api.example.com"]) is False


def test_configuration_validation():
    """Test that configuration validation always enforces audience settings."""
    # Should raise error when no audiences configured (always enforced now)
    with pytest.raises(ValueError, match="expected_audiences.*required for RFC 9068"):
        MCPAuthorizationServerSettings(
            enabled=True,
            issuer_url="https://auth.example.com",
            resource_server_url="https://api.example.com",
            expected_audiences=[],  # Empty list should always fail
        )

    # Should succeed with proper configuration
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com"],
    )
    assert "https://api.example.com" in settings.expected_audiences


@pytest.mark.asyncio
async def test_token_verifier_audience_validation_integration():
    """Test full integration of audience validation in token verifier."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        client_id="test-client",
        client_secret="test-secret",
        expected_audiences=["https://api.example.com"],
    )

    verifier = MCPAgentTokenVerifier(settings)

    # Mock HTTP client
    mock_client = Mock(spec=httpx.AsyncClient)

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

    # Mock successful response with valid audience
    valid_response = Mock()
    valid_response.status_code = 200
    valid_response.json.return_value = {
        "active": True,
        "aud": "https://api.example.com",
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }

    mock_client.get = AsyncMock(return_value=metadata_response)
    mock_client.post = AsyncMock(return_value=valid_response)
    verifier._client = mock_client

    # Should succeed with valid audience
    token = await verifier._introspect("valid_token")
    assert token is not None
    assert "https://api.example.com" in token.audiences

    # Mock response with invalid audience
    invalid_response = Mock()
    invalid_response.status_code = 200
    invalid_response.json.return_value = {
        "active": True,
        "aud": "https://malicious.example.com",  # Wrong audience
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }
    mock_client.post = AsyncMock(return_value=invalid_response)

    # Should fail with invalid audience
    token = await verifier._introspect("invalid_token")
    assert token is None


def test_audience_extraction_edge_cases():
    """Test audience extraction handles edge cases properly."""
    # Empty payload
    assert _extract_all_audiences({}) == []

    # None values
    assert _extract_all_audiences({"aud": None, "resource": None}) == []

    # Mixed empty and valid values
    payload = {
        "aud": ["", "https://valid.com", None],
        "resource": ["https://another.com", ""],
    }
    audiences = _extract_all_audiences(payload)
    expected = {"https://valid.com", "https://another.com"}
    assert set(audiences) == expected

    # Duplicate values should be removed
    payload = {
        "aud": ["https://api.com", "https://api.com"],
        "resource": "https://api.com",
    }
    audiences = _extract_all_audiences(payload)
    assert audiences == ["https://api.com"]


@pytest.mark.asyncio
async def test_partial_audience_match():
    """Test that partial audience matches are sufficient for validation."""
    settings = MCPAuthorizationServerSettings(
        enabled=True,
        issuer_url="https://auth.example.com",
        resource_server_url="https://api.example.com",
        expected_audiences=["https://api.example.com", "https://other-api.com"],
    )

    # Token has one matching and one non-matching audience
    payload = {
        "active": True,
        "aud": ["https://api.example.com", "https://unrelated.com"],
        "sub": "user123",
        "exp": 1234567890,
        "iss": "https://auth.example.com/",
    }

    token = MCPAccessToken.from_introspection("test_token", payload)
    # Should succeed because at least one audience matches
    assert token.validate_audience(settings.expected_audiences) is True
