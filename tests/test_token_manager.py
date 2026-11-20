from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import URL
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)

from mcp_agent.config import (
    MCPAuthorizationServerSettings,
    MCPOAuthClientSettings,
    OAuthSettings,
    Settings,
)
from mcp_agent.oauth.access_token import MCPAccessToken
from mcp_agent.oauth.errors import MissingUserIdentityError
from mcp_agent.oauth.identity import (
    DEFAULT_PRECONFIGURED_IDENTITY,
    OAuthUserIdentity,
    is_authenticated_identity,
    session_identity,
)
from mcp_agent.oauth.http.auth import OAuthHttpxAuth
from mcp_agent.oauth.manager import (
    ResolvedOAuthContext,
    TokenManager,
    _candidate_authorization_metadata_urls,
    _candidate_resource_metadata_urls,
)
from mcp_agent.oauth.store import InMemoryTokenStore


class DummyServerConfig:
    def __init__(self, oauth_config, url="https://api.example.com/mcp"):
        self.url = url
        self.auth = SimpleNamespace(oauth=oauth_config)


class DummyContext:
    def __init__(
        self,
        session_id: str | None,
        config=None,
    ):
        self.session_id = session_id
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
        context=DummyContext(session_id=None),
        server_name="github",
        server_config=server_config,
    )

    context = DummyContext(session_id="session-1")
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
        identity=DEFAULT_PRECONFIGURED_IDENTITY,
        resource=resolved.resource,
        authorization_server=resolved.issuer,
        scopes=resolved.scopes,
    )
    assert await store.get(key) is None


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

    context = DummyContext(session_id="session-xyz")
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


@pytest.mark.asyncio
async def test_store_user_token_rejects_default_and_invalid_identities():
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
    token_data = {"access_token": "token-123", "scopes": ["repo"]}

    for bad_identity in (
        None,
        DEFAULT_PRECONFIGURED_IDENTITY,
        OAuthUserIdentity(provider="mcp-agent", subject="preconfigured-tokens"),
        OAuthUserIdentity(
            provider="mcp-agent",
            subject="preconfigured-tokens",
            claims={"custom": "claim"},
        ),
        OAuthUserIdentity(
            provider="  mcp-agent  ",
            subject="  preconfigured-tokens  ",
        ),
        OAuthUserIdentity(provider="test", subject="   "),
        OAuthUserIdentity(provider="  ", subject="user-1"),
    ):
        assert not is_authenticated_identity(bad_identity)
        with pytest.raises(MissingUserIdentityError):
            await manager.store_user_token(
                context=DummyContext(session_id="sess-1"),
                user=bad_identity,  # type: ignore[arg-type]
                server_name="github",
                server_config=server_config,
                token_data=token_data,
            )

    auth_enabled_cfg = Settings(
        authorization=MCPAuthorizationServerSettings(
            enabled=True,
            issuer_url="https://auth.example.com",
            resource_server_url="https://api.example.com",
            expected_audiences=["https://api.example.com"],
        )
    )
    with pytest.raises(MissingUserIdentityError):
        await manager.store_user_token(
            context=DummyContext(session_id="sess-1", config=auth_enabled_cfg),
            user=session_identity("sess-1"),  # type: ignore[arg-type]
            server_name="github",
            server_config=server_config,
            token_data=token_data,
        )


@pytest.mark.asyncio
async def test_token_manager_enforces_auth_boundary_and_rejects_missing_auth_context():
    oauth_settings = OAuthSettings(
        callback_base_url="http://localhost:8000",
        flow_timeout_seconds=300,
    )
    auth_settings = Settings(
        authorization=MCPAuthorizationServerSettings(
            enabled=True,
            issuer_url="https://auth.example.com",
            resource_server_url="https://api.example.com",
            expected_audiences=["https://api.example.com"],
        ),
        oauth=oauth_settings,
    )
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=oauth_settings)

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        access_token="preconfigured-token",
        authorization_server="https://auth.example.com",
        resource="https://api.example.com/mcp",
        scopes=["read"],
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

    auth_ctx = DummyContext(session_id="shared-app-session", config=auth_settings)
    await manager.store_preconfigured_token(
        context=auth_ctx,
        server_name="github",
        server_config=server_config,
    )

    user_a = OAuthUserIdentity(provider="https://auth.example.com", subject="user-a")
    user_b = OAuthUserIdentity(provider="https://auth.example.com", subject="user-b")
    await manager.store_user_token(
        context=auth_ctx,
        user=user_a,
        server_name="github",
        server_config=server_config,
        token_data={"access_token": "token-a", "scopes": ["read"]},
    )

    # Missing auth context must be rejected when authorization is enabled.
    with pytest.raises(MissingUserIdentityError):
        await manager.get_access_token_if_present(
            context=auth_ctx,
            server_name="github",
            server_config=server_config,
        )
    with pytest.raises(MissingUserIdentityError):
        await manager.ensure_access_token(
            context=auth_ctx,
            server_name="github",
            server_config=server_config,
        )

    # Sub-less AuthenticatedUser in auth_context_var must also be rejected.
    subless_tok = auth_context_var.set(
        AuthenticatedUser(
            MCPAccessToken(
                token="bad",
                client_id="c1",
                scopes=["read"],
                subject=None,
                issuer="https://auth.example.com",
            )
        )
    )
    try:
        with pytest.raises(MissingUserIdentityError):
            await manager.ensure_access_token(
                context=auth_ctx,
                server_name="github",
                server_config=server_config,
            )
    finally:
        auth_context_var.reset(subless_tok)

    # User A gets User A's token; User B gets only the preconfigured token.
    rec_a = await manager.ensure_access_token(
        context=auth_ctx,
        server_name="github",
        server_config=server_config,
        identity=user_a,
    )
    rec_b = await manager.ensure_access_token(
        context=auth_ctx,
        server_name="github",
        server_config=server_config,
        identity=user_b,
    )
    assert rec_a.access_token == "token-a"
    assert rec_b.access_token == "preconfigured-token"


@pytest.mark.asyncio
async def test_oauth_httpx_auth_401_retry_resolves_identity_from_auth_context():
    import httpx

    from mcp_agent.oauth.records import TokenRecord
    from mcp_agent.server import app_server

    auth_settings = Settings(
        authorization=MCPAuthorizationServerSettings(
            enabled=True,
            issuer_url="https://auth.example.com",
            resource_server_url="https://api.example.com",
            expected_audiences=["https://api.example.com"],
        ),
    )
    auth_ctx = DummyContext(session_id="shared-session", config=auth_settings)
    server_config = DummyServerConfig(
        MCPOAuthClientSettings(
            enabled=True,
            authorization_server="https://auth.example.com",
            resource="https://api.example.com/mcp",
            scopes=["read"],
        )
    )

    first_record = TokenRecord(
        access_token="stale-token",
        scopes=("read",),
        resource="https://api.example.com/mcp",
        authorization_server="https://auth.example.com",
    )
    refreshed_record = TokenRecord(
        access_token="fresh-token",
        scopes=("read",),
        resource="https://api.example.com/mcp",
        authorization_server="https://auth.example.com",
    )
    manager = SimpleNamespace(
        ensure_access_token=AsyncMock(side_effect=[first_record, refreshed_record]),
        invalidate=AsyncMock(),
    )

    httpx_auth = OAuthHttpxAuth(
        token_manager=manager,  # type: ignore[arg-type]
        context=auth_ctx,  # type: ignore[arg-type]
        server_name="github",
        server_config=server_config,
        scopes=["read"],
    )

    # Ensure app_server current identity is None while auth_context_var has an authenticated user.
    app_server._set_current_identity(None)  # type: ignore[attr-defined]
    tok = auth_context_var.set(
        AuthenticatedUser(
            MCPAccessToken(
                token="access-1",
                client_id="client-1",
                scopes=["read"],
                subject="user-401",
                issuer="https://auth.example.com",
            )
        )
    )
    try:
        request = httpx.Request("GET", "https://api.example.com/mcp")
        flow = httpx_auth.async_auth_flow(request)
        first_req = await flow.asend(None)
        assert first_req.headers["Authorization"] == "Bearer stale-token"

        retry_req = await flow.asend(httpx.Response(401, request=first_req))
        assert retry_req.headers["Authorization"] == "Bearer fresh-token"

        expected_identity = OAuthUserIdentity(
            provider="https://auth.example.com",
            subject="user-401",
            claims={},
        )
        assert manager.invalidate.await_count == 1
        assert manager.invalidate.await_args.kwargs["identity"] == expected_identity
        assert manager.ensure_access_token.await_count == 2
        assert (
            manager.ensure_access_token.await_args_list[0].kwargs["identity"]
            == expected_identity
        )
        assert (
            manager.ensure_access_token.await_args_list[1].kwargs["identity"]
            == expected_identity
        )
    finally:
        auth_context_var.reset(tok)
        app_server._set_current_identity(None)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_temporal_execution_identity_used_when_authorization_enabled(monkeypatch):
    from mcp_agent.server import app_server

    manager = TokenManager(token_store=InMemoryTokenStore())
    auth_ctx = SimpleNamespace(
        session_id="shared-session",
        config=SimpleNamespace(
            authorization=SimpleNamespace(enabled=True),
        ),
    )
    exec_user = OAuthUserIdentity(
        provider="https://auth.example.com", subject="temporal-user-1"
    )
    monkeypatch.setattr(manager, "_temporal_execution_identity", lambda: exec_user)

    app_server._set_current_identity(None)  # type: ignore[attr-defined]
    candidates, flow_identity = manager._resolve_identity_candidates(
        auth_ctx,  # type: ignore[arg-type]
        None,
    )
    assert flow_identity == exec_user
    assert candidates == [exec_user, DEFAULT_PRECONFIGURED_IDENTITY]

    # Unauthenticated / synthetic session identity from temporal registry must still be rejected.
    synthetic = OAuthUserIdentity(provider="mcp-session", subject="shared-session")
    monkeypatch.setattr(manager, "_temporal_execution_identity", lambda: synthetic)
    with pytest.raises(MissingUserIdentityError):
        manager._resolve_identity_candidates(auth_ctx, None)  # type: ignore[arg-type]
