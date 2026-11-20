from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from mcp_agent.config import (
    MCPAuthorizationServerSettings,
    MCPOAuthClientSettings,
    OAuthSettings,
    Settings,
)
from mcp_agent.core.context import Context
from mcp_agent.oauth.access_token import MCPAccessToken
from mcp_agent.oauth.errors import MissingUserIdentityError
from mcp_agent.oauth.identity import DEFAULT_PRECONFIGURED_IDENTITY, OAuthUserIdentity
from mcp_agent.oauth.manager import ResolvedOAuthContext, TokenManager
from mcp_agent.oauth.store import InMemoryTokenStore
from mcp_agent.server import app_server


class DummyRequestContext:
    def __init__(self, session_id: str, session_obj):
        self.meta = SimpleNamespace(sessionId=session_id)
        self.metadata = SimpleNamespace(session_id=session_id)
        self.extra = {"session_id": session_id}
        self.session = session_obj
        self.request = SimpleNamespace(path=f"/rpc?session_id={session_id}")


class DummyMCPContext:
    def __init__(self, session_id: str, fastmcp: FastMCP, session_obj=None):
        self._session_obj = session_obj or object()
        self.request_context = DummyRequestContext(session_id, self._session_obj)
        self.fastmcp = fastmcp

    @property
    def session(self):
        return self.request_context.session


def make_attached_app():
    fastmcp = FastMCP(name="test", instructions="test")
    app_context = Context()
    app_context.session_id = "app-session"
    app = SimpleNamespace(
        context=app_context,
        _session_id_override="app-default",
    )
    setattr(fastmcp, "_mcp_agent_app", app)
    return fastmcp, app, app_context


def reset_identity():
    app_server._set_current_identity(None)  # type: ignore[attr-defined]


def test_set_upstream_updates_session_each_request():
    fastmcp, app, app_context = make_attached_app()

    try:
        ctx1 = DummyMCPContext("session-one", fastmcp)
        bound_ctx1, token1 = app_server._enter_request_context(ctx1)  # type: ignore[attr-defined]

        assert bound_ctx1.upstream_session is ctx1.session
        assert app_context.upstream_session is ctx1.session
        assert "session-one" in app_context.identity_registry
        assert app_context.identity_registry["session-one"].subject == "session-one"
        assert app_context.session_id == "app-session"
        app_server._exit_request_context(bound_ctx1, token1)
        assert app_context.upstream_session is None

        ctx2 = DummyMCPContext("session-two", fastmcp)
        bound_ctx2, token2 = app_server._enter_request_context(ctx2)  # type: ignore[attr-defined]

        assert bound_ctx2.upstream_session is ctx2.session
        assert app_context.upstream_session is ctx2.session
        assert "session-two" in app_context.identity_registry
        assert app_context.identity_registry["session-two"].subject == "session-two"
        assert app_context.identity_registry["session-one"].subject == "session-one"
        assert app_context.session_id == "app-session"
        app_server._exit_request_context(bound_ctx2, token2)
        assert app_context.upstream_session is None
    finally:
        reset_identity()


def test_resolve_identity_prefers_request_session(monkeypatch):
    fastmcp, app, app_context = make_attached_app()
    ctx = DummyMCPContext("client-session", fastmcp)
    bound_ctx, token = app_server._enter_request_context(ctx)  # type: ignore[attr-defined]
    identity = app_server._resolve_identity_for_request(  # type: ignore[attr-defined]
        ctx=ctx,
        app_context=app_context,
        execution_id=None,
    )
    assert isinstance(identity, OAuthUserIdentity)
    assert identity.subject == "client-session"
    app_server._exit_request_context(bound_ctx, token)


def _auth_enabled_settings() -> Settings:
    return Settings(
        authorization=MCPAuthorizationServerSettings(
            enabled=True,
            issuer_url="https://auth.example.com",
            resource_server_url="https://api.example.com",
            expected_audiences=["https://api.example.com"],
        ),
        oauth=OAuthSettings(
            callback_base_url="https://api.example.com",
            flow_timeout_seconds=300,
        ),
    )


@pytest.mark.parametrize(
    "bad_token",
    [
        AccessToken(token="tok", client_id="c1", scopes=[]),
        MCPAccessToken(token="tok", client_id="c1", scopes=[], subject=None),
        MCPAccessToken(token="tok", client_id="c1", scopes=[], subject=""),
        MCPAccessToken(token="tok", client_id="c1", scopes=[], subject="   "),
    ],
)
def test_enter_request_context_rejects_authenticated_user_without_sub(bad_token):
    fastmcp, _, app_context = make_attached_app()
    ctx = DummyMCPContext("attacker-session", fastmcp)
    auth_tok = auth_context_var.set(AuthenticatedUser(bad_token))
    try:
        with pytest.raises(MissingUserIdentityError, match="sub"):
            app_server._enter_request_context(ctx)  # type: ignore[attr-defined]
        with pytest.raises(MissingUserIdentityError, match="sub"):
            app_server._resolve_identity_for_request(  # type: ignore[attr-defined]
                ctx=ctx, app_context=app_context
            )
        assert app_server.get_current_identity() is None
    finally:
        auth_context_var.reset(auth_tok)
        reset_identity()


def test_enter_request_context_rejects_missing_auth_when_authorization_enabled():
    fastmcp, _, app_context = make_attached_app()
    app_context.config = _auth_enabled_settings()
    ctx = DummyMCPContext("session-spoof", fastmcp)
    try:
        with pytest.raises(MissingUserIdentityError, match="authenticated"):
            app_server._enter_request_context(ctx)  # type: ignore[attr-defined]
        with pytest.raises(MissingUserIdentityError, match="authenticated"):
            app_server._resolve_identity_for_request(  # type: ignore[attr-defined]
                ctx=ctx, app_context=app_context
            )
    finally:
        reset_identity()


def test_enter_request_context_accepts_authenticated_user_with_valid_sub():
    fastmcp, _, app_context = make_attached_app()
    app_context.config = _auth_enabled_settings()
    ctx = DummyMCPContext("client-session", fastmcp)
    valid_token = MCPAccessToken(
        token="tok-valid",
        client_id="c1",
        scopes=["mcp"],
        subject="user-a",
        issuer="https://auth.example.com",
    )
    auth_tok = auth_context_var.set(AuthenticatedUser(valid_token))
    try:
        bound_ctx, token = app_server._enter_request_context(ctx)  # type: ignore[attr-defined]
        try:
            identity = app_server._resolve_identity_for_request(  # type: ignore[attr-defined]
                ctx=ctx, app_context=app_context
            )
            assert identity == OAuthUserIdentity(
                provider="https://auth.example.com",
                subject="user-a",
                claims={},
            )
        finally:
            app_server._exit_request_context(bound_ctx, token)
    finally:
        auth_context_var.reset(auth_tok)
        reset_identity()


@pytest.mark.asyncio
async def test_workflows_store_credentials_isolates_buckets_and_rejects_bad_auth():
    settings = _auth_enabled_settings()
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=settings.oauth)
    resolved = ResolvedOAuthContext(
        resource="https://downstream.example.com/mcp",
        resource_metadata=SimpleNamespace(),
        authorization_server_url="https://auth.example.com",
        authorization_metadata=SimpleNamespace(issuer="https://auth.example.com"),
        issuer="https://auth.example.com",
        scopes=("read",),
    )
    manager._resolve_oauth_context = AsyncMock(return_value=resolved)  # type: ignore[attr-defined]

    oauth_client_cfg = MCPOAuthClientSettings(
        enabled=True,
        access_token="preconfigured-secret",
        authorization_server="https://auth.example.com",
        resource="https://downstream.example.com/mcp",
        scopes=["read"],
    )
    downstream_cfg = SimpleNamespace(
        url="https://downstream.example.com/mcp",
        auth=SimpleNamespace(oauth=oauth_client_cfg),
    )

    app_context = Context(config=settings)
    app_context.token_manager = manager
    app_context.server_registry = SimpleNamespace(registry={"github": downstream_cfg})
    await manager.store_preconfigured_token(
        context=app_context,
        server_name="github",
        server_config=downstream_cfg,
    )

    app = SimpleNamespace(
        name="test-app",
        description="test",
        context=app_context,
        workflows={"demo_workflow": object()},
        mcp=None,
        _icons=None,
    )
    mcp = app_server.create_mcp_server_for_app(app)  # type: ignore[arg-type]
    store_tool = mcp._tool_manager.get_tool("workflows-store-credentials")
    assert store_tool is not None

    # 1) Missing auth context must be rejected and leave preconfigured token intact.
    ctx_no_auth = DummyMCPContext("", fastmcp=mcp)
    with pytest.raises((ToolError, MissingUserIdentityError)):
        await store_tool.fn(
            ctx=ctx_no_auth,
            workflow_name="demo_workflow",
            tokens=[{"access_token": "attacker-token", "server_name": "github"}],
        )

    # 2) Authenticated user missing 'sub' must be rejected and not touch preconfigured bucket.
    subless_token = MCPAccessToken(
        token="subless",
        client_id="client-a",
        scopes=["mcp"],
        subject=None,
        issuer="https://auth.example.com",
    )
    tok_subless = auth_context_var.set(AuthenticatedUser(subless_token))
    try:
        with pytest.raises((ToolError, MissingUserIdentityError)):
            await store_tool.fn(
                ctx=ctx_no_auth,
                workflow_name="demo_workflow",
                tokens=[{"access_token": "attacker-token", "server_name": "github"}],
            )
    finally:
        auth_context_var.reset(tok_subless)
        reset_identity()

    # 3) Authenticated User A stores credentials -> isolated to User A's bucket only.
    user_a_token = MCPAccessToken(
        token="tok-a",
        client_id="client-a",
        scopes=["mcp"],
        subject="user-a",
        issuer="https://auth.example.com",
    )
    tok_a = auth_context_var.set(AuthenticatedUser(user_a_token))
    try:
        res = await store_tool.fn(
            ctx=ctx_no_auth,
            workflow_name="demo_workflow",
            tokens=[{"access_token": "user-a-downstream", "server_name": "github"}],
        )
        assert res["success"] is True
        assert res["stored_tokens"] == 1
    finally:
        auth_context_var.reset(tok_a)
        reset_identity()

    # Verify User A sees User A's token, User B sees ONLY preconfigured token, and default bucket wasn't overwritten.
    default_key = manager._build_store_key(
        DEFAULT_PRECONFIGURED_IDENTITY,
        resolved.resource,
        resolved.issuer,
        resolved.scopes,
    )
    default_record = await store.get(default_key)
    assert default_record is not None
    assert default_record.access_token == "preconfigured-secret"

    user_a_identity = OAuthUserIdentity(
        provider="https://auth.example.com", subject="user-a"
    )
    user_b_identity = OAuthUserIdentity(
        provider="https://auth.example.com", subject="user-b"
    )
    record_a = await manager.ensure_access_token(
        context=app_context,
        server_name="github",
        server_config=downstream_cfg,
        identity=user_a_identity,
    )
    record_b = await manager.ensure_access_token(
        context=app_context,
        server_name="github",
        server_config=downstream_cfg,
        identity=user_b_identity,
    )
    assert record_a.access_token == "user-a-downstream"
    assert record_b.access_token == "preconfigured-secret"


@pytest.mark.asyncio
async def test_workflows_store_credentials_rejects_default_identity_without_session():
    settings = Settings(
        oauth=OAuthSettings(
            callback_base_url="http://localhost:8000",
            flow_timeout_seconds=300,
        )
    )
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=settings.oauth)
    downstream_cfg = SimpleNamespace(
        url="https://downstream.example.com/mcp",
        auth=SimpleNamespace(
            oauth=MCPOAuthClientSettings(
                enabled=True,
                authorization_server="https://auth.example.com",
                resource="https://downstream.example.com/mcp",
                scopes=["read"],
            )
        ),
    )

    app_context = Context(config=settings)
    app_context.token_manager = manager
    app_context.server_registry = SimpleNamespace(registry={"github": downstream_cfg})
    app = SimpleNamespace(
        name="test-app",
        description="test",
        context=app_context,
        workflows={"demo_workflow": object()},
        mcp=None,
        _icons=None,
    )
    mcp = app_server.create_mcp_server_for_app(app)  # type: ignore[arg-type]
    store_tool = mcp._tool_manager.get_tool("workflows-store-credentials")

    ctx_no_session = DummyMCPContext("", fastmcp=mcp)
    with pytest.raises(ToolError, match="authenticated user or session"):
        await store_tool.fn(
            ctx=ctx_no_session,
            workflow_name="demo_workflow",
            tokens=[{"access_token": "tok", "server_name": "github"}],
        )
    reset_identity()


@pytest.mark.asyncio
async def test_internal_auth_request_propagates_missing_user_identity_error():
    from starlette.requests import Request

    settings = _auth_enabled_settings()
    store = InMemoryTokenStore()
    manager = TokenManager(token_store=store, settings=settings.oauth)
    resolved = ResolvedOAuthContext(
        resource="https://downstream.example.com/mcp",
        resource_metadata=SimpleNamespace(),
        authorization_server_url="https://auth.example.com",
        authorization_metadata=SimpleNamespace(issuer="https://auth.example.com"),
        issuer="https://auth.example.com",
        scopes=("read",),
    )
    manager._resolve_oauth_context = AsyncMock(return_value=resolved)  # type: ignore[attr-defined]

    downstream_cfg = SimpleNamespace(
        url="https://downstream.example.com/mcp",
        auth=SimpleNamespace(
            oauth=MCPOAuthClientSettings(
                enabled=True,
                authorization_server="https://auth.example.com",
                resource="https://downstream.example.com/mcp",
                scopes=["read"],
            )
        ),
    )

    app_context = Context(config=settings)
    app_context.token_manager = manager
    app_context.server_registry = SimpleNamespace(
        registry={"github": downstream_cfg},
        get_server_config=lambda name: downstream_cfg if name == "github" else None,
    )
    app = SimpleNamespace(
        name="test-app",
        description="test",
        context=app_context,
        workflows={"demo_workflow": object()},
        mcp=None,
        _icons=None,
    )
    mcp = app_server.create_mcp_server_for_app(app)  # type: ignore[arg-type]

    relay_route = next(
        r
        for r in mcp._custom_starlette_routes
        if getattr(r, "path", None) == "/internal/session/by-run/{execution_id}/request"
    )

    dummy_session = SimpleNamespace(send_request=AsyncMock())
    await app_server._register_session(  # type: ignore[attr-defined]
        run_id="exec-no-identity",
        execution_id="exec-no-identity",
        session=dummy_session,
        identity=None,
        context=app_context,
    )

    body_bytes = b'{"method": "auth/request", "params": {"server_name": "github", "scopes": ["read"]}}'

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/internal/session/by-run/exec-no-identity/request",
        "path_params": {"execution_id": "exec-no-identity"},
        "headers": [(b"content-type", b"application/json")],
    }
    req = Request(scope, receive)

    try:
        resp = await relay_route.endpoint(req)
        assert resp.status_code == 500
        assert b"No authenticated user available" in resp.body
        assert dummy_session.send_request.await_count == 0
    finally:
        await app_server._unregister_session("exec-no-identity")  # type: ignore[attr-defined]
        reset_identity()
