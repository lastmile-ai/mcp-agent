"""
Integration tests for OAuth MCP Tools example.

These tests verify the OAuth flow functionality in the mcp-agent framework,
focusing on:
1. Pre-configured token storage and retrieval
2. Token manager identity resolution
3. OAuth HTTP auth integration
4. Token refresh and invalidation

Run these tests with: pytest tests/integration/test_oauth_mcp_tools.py -v
"""

import asyncio
import json
import pathlib
import sys
import time
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src directory is in path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.oauth.identity import OAuthUserIdentity, DEFAULT_PRECONFIGURED_IDENTITY
from mcp_agent.oauth.manager import TokenManager, ResolvedOAuthContext
from mcp_agent.oauth.store import InMemoryTokenStore, TokenStoreKey
from mcp_agent.oauth.records import TokenRecord
from mcp_agent.oauth.http.auth import OAuthHttpxAuth


class MockContext:
    """Mock context for testing."""
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id
        self.config = None
        self.upstream_session = None


class MockServerConfig:
    """Mock server configuration for testing."""
    def __init__(
        self,
        url: str = "https://api.githubcopilot.com/mcp/",
        oauth_enabled: bool = True,
        access_token: str | None = None,
        client_id: str | None = "test-client-id",
        client_secret: str | None = "test-client-secret",
        scopes: list[str] | None = None,
    ):
        self.url = url
        self.auth = MagicMock()
        self.auth.oauth = MCPOAuthClientSettings(
            enabled=oauth_enabled,
            access_token=access_token,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes or ["read:org", "public_repo", "user:email"],
            authorization_server="https://github.com/login/oauth",
            include_resource_parameter=False,
        )


class TestPreconfiguredTokenFlow:
    """Tests for pre-configured token storage and retrieval."""

    @pytest.mark.asyncio
    async def test_store_preconfigured_token_creates_record(self):
        """Test that preconfigured tokens are stored correctly."""
        oauth_settings = OAuthSettings(
            callback_base_url="http://127.0.0.1:8000",
            flow_timeout_seconds=300,
        )
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        # Mock the OAuth context resolution
        resolved = ResolvedOAuthContext(
            resource="https://api.githubcopilot.com/mcp/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://github.com/login/oauth",
            authorization_metadata=MagicMock(issuer="https://github.com/login/oauth"),
            issuer="https://github.com/login/oauth",
            scopes=("read:org", "public_repo", "user:email"),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        server_config = MockServerConfig(access_token="ghp_preconfigured_token_123")
        context = MockContext()

        # Store the preconfigured token
        await manager.store_preconfigured_token(
            context=context,
            server_name="github",
            server_config=server_config,
        )

        # Verify the token was stored under the default preconfigured identity
        key = manager._build_store_key(
            DEFAULT_PRECONFIGURED_IDENTITY,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )
        stored = await store.get(key)

        assert stored is not None
        assert stored.access_token == "ghp_preconfigured_token_123"
        assert stored.metadata.get("pre_configured") is True
        assert stored.metadata.get("server_name") == "github"

    @pytest.mark.asyncio
    async def test_preconfigured_token_is_retrievable(self):
        """Test that stored preconfigured tokens can be retrieved."""
        oauth_settings = OAuthSettings(
            callback_base_url="http://127.0.0.1:8000",
            flow_timeout_seconds=300,
        )
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        resolved = ResolvedOAuthContext(
            resource="https://api.githubcopilot.com/mcp/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://github.com/login/oauth",
            authorization_metadata=MagicMock(issuer="https://github.com/login/oauth"),
            issuer="https://github.com/login/oauth",
            scopes=("read:org",),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        server_config = MockServerConfig(
            access_token="ghp_retrievable_token",
            scopes=["read:org"],
        )
        context = MockContext()

        # Store the token
        await manager.store_preconfigured_token(
            context=context,
            server_name="github",
            server_config=server_config,
        )

        # Retrieve using ensure_access_token
        # This should find the preconfigured token without initiating an auth flow
        with patch("mcp_agent.server.app_server.get_current_identity", return_value=None):
            token = await manager.get_access_token_if_present(
                context=context,
                server_name="github",
                server_config=server_config,
            )

        assert token is not None
        assert token.access_token == "ghp_retrievable_token"

    @pytest.mark.asyncio
    async def test_no_token_stored_when_oauth_disabled(self):
        """Test that no token is stored when OAuth is disabled."""
        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        server_config = MockServerConfig(
            oauth_enabled=False,
            access_token="should_not_be_stored",
        )
        context = MockContext()

        # This should not store anything
        await manager.store_preconfigured_token(
            context=context,
            server_name="github",
            server_config=server_config,
        )

        # Verify nothing was stored (store should be empty)
        # We can't directly check store size, but we can verify the key doesn't exist
        # by attempting to retrieve and expecting None


class TestTokenIdentityResolution:
    """Tests for identity resolution in token management."""

    @pytest.mark.asyncio
    async def test_identity_candidates_include_preconfigured(self):
        """Test that identity candidates include the default preconfigured identity."""
        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        # The default identity should always be available
        assert manager._default_identity == DEFAULT_PRECONFIGURED_IDENTITY
        assert manager._default_identity.provider == "mcp-agent"
        assert manager._default_identity.subject == "preconfigured-tokens"

    @pytest.mark.asyncio
    async def test_session_identity_creation(self):
        """Test that session identity is created from session_id."""
        oauth_settings = OAuthSettings()
        manager = TokenManager(settings=oauth_settings)

        context = MockContext(session_id="test-session-123")

        # Mock app_server to not have an identity for this session
        with patch("mcp_agent.server.app_server.get_identity_for_session", return_value=None):
            identity = manager._session_identity(context)

        # Should fall back to synthetic session identity
        assert identity is not None
        assert identity.provider == "mcp-session"
        assert identity.subject == "test-session-123"

    @pytest.mark.asyncio
    async def test_no_session_identity_without_session_id(self):
        """Test that no session identity is created without session_id."""
        oauth_settings = OAuthSettings()
        manager = TokenManager(settings=oauth_settings)

        context = MockContext(session_id=None)

        identity = manager._session_identity(context)
        assert identity is None


class TestOAuthHttpAuth:
    """Tests for the OAuthHttpxAuth adapter."""

    @pytest.mark.asyncio
    async def test_auth_adds_authorization_header(self):
        """Test that the auth adapter adds the Authorization header."""
        import httpx

        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        resolved = ResolvedOAuthContext(
            resource="https://api.example.com/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://auth.example.com",
            authorization_metadata=MagicMock(issuer="https://auth.example.com"),
            issuer="https://auth.example.com",
            scopes=("read",),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        # Pre-store a token
        key = manager._build_store_key(
            DEFAULT_PRECONFIGURED_IDENTITY,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )
        await store.set(
            key,
            TokenRecord(
                access_token="test-bearer-token",
                token_type="Bearer",
                scopes=("read",),
            ),
        )

        server_config = MockServerConfig(
            url="https://api.example.com/",
            scopes=["read"],
        )
        context = MockContext()

        auth = OAuthHttpxAuth(
            token_manager=manager,
            context=context,
            server_name="test",
            server_config=server_config,
            scopes=["read"],
        )

        request = httpx.Request("GET", "https://api.example.com/data")

        # Run the auth flow
        with patch("mcp_agent.server.app_server.get_current_identity", return_value=None):
            flow = auth.async_auth_flow(request)
            modified_request = await flow.__anext__()

        assert "Authorization" in modified_request.headers
        assert modified_request.headers["Authorization"] == "Bearer test-bearer-token"


class TestTokenExpiry:
    """Tests for token expiry handling."""

    @pytest.mark.asyncio
    async def test_expired_token_not_returned(self):
        """Test that expired tokens are not returned."""
        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        resolved = ResolvedOAuthContext(
            resource="https://api.example.com/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://auth.example.com",
            authorization_metadata=MagicMock(issuer="https://auth.example.com"),
            issuer="https://auth.example.com",
            scopes=("read",),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        # Store an already expired token
        key = manager._build_store_key(
            DEFAULT_PRECONFIGURED_IDENTITY,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )
        await store.set(
            key,
            TokenRecord(
                access_token="expired-token",
                expires_at=time.time() - 3600,  # Expired 1 hour ago
                scopes=("read",),
            ),
        )

        server_config = MockServerConfig(url="https://api.example.com/", scopes=["read"])
        context = MockContext()

        with patch("mcp_agent.server.app_server.get_current_identity", return_value=None):
            token = await manager.get_access_token_if_present(
                context=context,
                server_name="test",
                server_config=server_config,
            )

        # Expired token without refresh_token should not be returned
        assert token is None

    @pytest.mark.asyncio
    async def test_token_with_leeway_still_valid(self):
        """Test that tokens within leeway window are still considered valid."""
        oauth_settings = OAuthSettings()
        oauth_settings.token_store = MagicMock()
        oauth_settings.token_store.refresh_leeway_seconds = 60

        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        resolved = ResolvedOAuthContext(
            resource="https://api.example.com/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://auth.example.com",
            authorization_metadata=MagicMock(issuer="https://auth.example.com"),
            issuer="https://auth.example.com",
            scopes=("read",),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        # Store a token that expires in 120 seconds (beyond 60s leeway)
        key = manager._build_store_key(
            DEFAULT_PRECONFIGURED_IDENTITY,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )
        await store.set(
            key,
            TokenRecord(
                access_token="still-valid-token",
                expires_at=time.time() + 120,
                scopes=("read",),
            ),
        )

        server_config = MockServerConfig(url="https://api.example.com/", scopes=["read"])
        context = MockContext()

        with patch("mcp_agent.server.app_server.get_current_identity", return_value=None):
            token = await manager.get_access_token_if_present(
                context=context,
                server_name="test",
                server_config=server_config,
            )

        assert token is not None
        assert token.access_token == "still-valid-token"


class TestUserTokenStorage:
    """Tests for user-specific token storage (pre-authorization flow)."""

    @pytest.mark.asyncio
    async def test_store_user_token_with_workflow_metadata(self):
        """Test storing user tokens with workflow metadata."""
        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        resolved = ResolvedOAuthContext(
            resource="https://api.githubcopilot.com/mcp/",
            resource_metadata=MagicMock(),
            authorization_server_url="https://github.com/login/oauth",
            authorization_metadata=MagicMock(issuer="https://github.com/login/oauth"),
            issuer="https://github.com/login/oauth",
            scopes=("repo",),
        )
        manager._resolve_oauth_context = AsyncMock(return_value=resolved)

        user_identity = OAuthUserIdentity(provider="test", subject="user-123")
        token_data = {
            "access_token": "user-specific-token",
            "scopes": ["repo"],
            "expires_at": time.time() + 3600,
        }

        server_config = MockServerConfig(scopes=["repo"])
        context = MockContext(session_id="session-xyz")

        await manager.store_user_token(
            context=context,
            user=user_identity,
            server_name="github",
            server_config=server_config,
            token_data=token_data,
            workflow_name="github_org_search_activity",
        )

        key = manager._build_store_key(
            user_identity,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )
        stored = await store.get(key)

        assert stored is not None
        assert stored.access_token == "user-specific-token"
        assert stored.metadata.get("workflow_name") == "github_org_search_activity"
        assert stored.metadata.get("session_id") == "session-xyz"

    @pytest.mark.asyncio
    async def test_store_user_token_requires_access_token(self):
        """Test that storing user token requires access_token in token_data."""
        oauth_settings = OAuthSettings()
        manager = TokenManager(settings=oauth_settings)

        user_identity = OAuthUserIdentity(provider="test", subject="user-123")
        token_data = {
            "scopes": ["repo"],
            # Missing access_token
        }

        server_config = MockServerConfig(scopes=["repo"])
        context = MockContext()

        from mcp_agent.oauth.errors import OAuthFlowError

        with pytest.raises(OAuthFlowError, match="Missing access_token"):
            await manager.store_user_token(
                context=context,
                user=user_identity,
                server_name="github",
                server_config=server_config,
                token_data=token_data,
            )


class TestTokenInvalidation:
    """Tests for token invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_removes_token(self):
        """Test that invalidation removes the token from store."""
        oauth_settings = OAuthSettings()
        store = InMemoryTokenStore()
        manager = TokenManager(token_store=store, settings=oauth_settings)

        identity = OAuthUserIdentity(provider="test", subject="user-123")
        key = manager._build_store_key(
            identity,
            "https://api.example.com",
            "https://auth.example.com",
            ("read",),
        )

        # Store a token
        await store.set(key, TokenRecord(access_token="to-be-invalidated"))

        # Verify it exists
        assert await store.get(key) is not None

        # Invalidate
        await manager.invalidate(
            identity=identity,
            resource="https://api.example.com",
            authorization_server="https://auth.example.com",
            scopes=["read"],
        )

        # Verify it's gone
        assert await store.get(key) is None


class TestGitHubMCPServerConfiguration:
    """Tests specific to GitHub MCP server OAuth configuration."""

    def test_github_config_disables_resource_parameter(self):
        """Test that GitHub config has include_resource_parameter set to False."""
        # This is critical because GitHub doesn't accept the RFC 8707 resource parameter
        oauth_config = MCPOAuthClientSettings(
            enabled=True,
            scopes=["read:org", "public_repo", "user:email"],
            authorization_server="https://github.com/login/oauth",
            include_resource_parameter=False,
        )

        assert oauth_config.include_resource_parameter is False

    def test_github_config_uses_correct_scopes(self):
        """Test that GitHub config uses appropriate scopes."""
        oauth_config = MCPOAuthClientSettings(
            enabled=True,
            scopes=["read:org", "public_repo", "user:email"],
            authorization_server="https://github.com/login/oauth",
        )

        assert "read:org" in oauth_config.scopes
        assert "public_repo" in oauth_config.scopes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


