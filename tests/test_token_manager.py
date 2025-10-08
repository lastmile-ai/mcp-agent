from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import URL

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.oauth.identity import OAuthUserIdentity, DEFAULT_PRECONFIGURED_IDENTITY
from mcp_agent.oauth.manager import (
    ResolvedOAuthContext,
    TokenManager,
    _candidate_authorization_metadata_urls,
    _candidate_resource_metadata_urls,
)
from mcp_agent.oauth.records import TokenRecord
from mcp_agent.oauth.store import InMemoryTokenStore
from mcp_agent.oauth.context_state import identity_scope


class DummyServerConfig:
    def __init__(self, oauth_config, url="https://api.example.com/mcp"):
        self.url = url
        self.auth = SimpleNamespace(oauth=oauth_config)


class DummyContext:
    def __init__(
        self,
        session_id: str | None,
        current_user: OAuthUserIdentity | None,
        config=None,
    ):
        self.session_id = session_id
        self.current_user = current_user
        self.config = config


@pytest.mark.asyncio
async def test_preconfigured_token_lookup_and_invalidation():
    oauth_settings = OAuthSettings(
        callback_base_url="http://localhost:8000",
        flow_timeout_seconds=300,
    )
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=oauth_settings)

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        access_token="preconfigured-token",
        authorization_server="https://auth.example.com",
        resource="https://api.example.com/mcp",
    )
    server_config = DummyServerConfig(oauth_config)

    resolved = ResolvedOAuthContext(
        resource="https://api.example.com/mcp",
        resource_metadata=SimpleNamespace(),
        authorization_server_url="https://auth.example.com",
        authorization_metadata=SimpleNamespace(issuer="https://auth.example.com"),
        issuer="https://auth.example.com",
        scopes=("read",),
    )

    manager._resolve_oauth_context = AsyncMock(return_value=resolved)  # type: ignore[attr-defined]

    await manager.store_preconfigured_token(
        context=DummyContext(session_id=None, current_user=None),
        server_name="github",
        server_config=server_config,
    )

    context = DummyContext(session_id="session-1", current_user=None)
    token = await manager.ensure_access_token(
        context=context,
        server_name="github",
        server_config=server_config,
    )
    assert token.access_token == "preconfigured-token"

    key = manager._build_store_key(
        DEFAULT_PRECONFIGURED_IDENTITY,
        resolved.resource,
        resolved.issuer,
        resolved.scopes,
    )
    await manager.invalidate(
        user=DEFAULT_PRECONFIGURED_IDENTITY,
        resource=resolved.resource,
        authorization_server=resolved.issuer,
        scopes=resolved.scopes,
        session_id=context.session_id,
    )
    assert await store.get(key) is None


@pytest.mark.asyncio
async def test_scoped_identity_used_when_context_user_missing():
    oauth_settings = OAuthSettings(
        callback_base_url="http://localhost:8000",
        flow_timeout_seconds=300,
    )
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=oauth_settings)

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        authorization_server="https://auth.example.com",
        resource="https://api.example.com/mcp",
    )
    server_config = DummyServerConfig(oauth_config)

    resolved = ResolvedOAuthContext(
        resource="https://api.example.com/mcp",
        resource_metadata=SimpleNamespace(),
        authorization_server_url="https://auth.example.com",
        authorization_metadata=SimpleNamespace(issuer="https://auth.example.com"),
        issuer="https://auth.example.com",
        scopes=("repo",),
    )
    manager._resolve_oauth_context = AsyncMock(return_value=resolved)  # type: ignore[attr-defined]

    token_record = TokenRecord(access_token="abc", scopes=("repo",))
    manager._token_store.set = AsyncMock()  # type: ignore[attr-defined]
    manager._flow.authorize = AsyncMock(return_value=token_record)  # type: ignore[attr-defined]

    scoped_identity = OAuthUserIdentity(provider="scoped", subject="user-42")
    context = DummyContext(session_id=None, current_user=None)

    with identity_scope(scoped_identity):
        await manager.ensure_access_token(
            context=context,
            server_name="github",
            server_config=server_config,
        )

    manager._flow.authorize.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_store_user_token_uses_workflow_and_session_metadata():
    oauth_settings = OAuthSettings(
        callback_base_url="http://localhost:8000",
        flow_timeout_seconds=300,
    )
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=oauth_settings)

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        authorization_server="https://auth.example.com",
        resource="https://api.example.com/mcp",
    )
    server_config = DummyServerConfig(oauth_config)

    resolved = ResolvedOAuthContext(
        resource="https://api.example.com/mcp",
        resource_metadata=SimpleNamespace(),
        authorization_server_url="https://auth.example.com",
        authorization_metadata=SimpleNamespace(issuer="https://auth.example.com"),
        issuer="https://auth.example.com",
        scopes=("repo",),
    )
    manager._resolve_oauth_context = AsyncMock(return_value=resolved)  # type: ignore[attr-defined]

    user_identity = OAuthUserIdentity(provider="test", subject="user-123")
    token_data = {
        "access_token": "token-123",
        "scopes": ["repo"],
        "expires_at": 0,
    }

    context = DummyContext(session_id="session-xyz", current_user=user_identity)
    await manager.store_user_token(
        context=context,
        user=user_identity,
        server_name="github",
        server_config=server_config,
        token_data=token_data,
        workflow_name="example_workflow",
    )

    key = manager._build_store_key(
        user_identity,
        resolved.resource,
        resolved.issuer,
        resolved.scopes,
    )
    stored = await store.get(key)
    assert stored is not None
    assert stored.access_token == "token-123"
    assert stored.metadata.get("workflow_name") == "example_workflow"
    assert stored.metadata.get("session_id") == "session-xyz"


def test_candidate_resource_metadata_urls():
    parsed = URL("https://api.example.com/mcp")
    urls = _candidate_resource_metadata_urls(parsed)
    assert urls[0].endswith("/.well-known/oauth-protected-resource/mcp")
    assert urls[1].endswith("/.well-known/oauth-protected-resource")


def test_candidate_authorization_metadata_urls():
    parsed = URL("https://auth.example.com/tenant")
    urls = _candidate_authorization_metadata_urls(parsed)
    assert urls[0].endswith("/.well-known/oauth-authorization-server/tenant")
    assert urls[1].endswith("/.well-known/oauth-authorization-server")
