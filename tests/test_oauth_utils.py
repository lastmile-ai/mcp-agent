import time
import asyncio
import pathlib
import sys
from typing import Any, Dict

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    from mcp_agent.oauth.metadata import normalize_resource, select_authorization_server
    from mcp_agent.oauth.records import TokenRecord
    from mcp_agent.oauth.store import (
        InMemoryTokenStore,
        TokenStoreKey,
        scope_fingerprint,
    )
    from mcp.shared.auth import ProtectedResourceMetadata
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pytest.skip("MCP SDK not installed", allow_module_level=True)


def test_scope_fingerprint_ordering():
    scopes = ["email", "profile", "email"]
    fingerprint = scope_fingerprint(scopes)
    assert fingerprint == "email profile"


def test_token_record_expiry():
    record = TokenRecord(
        access_token="tok",
        expires_at=time.time() + 5,
    )
    assert not record.is_expired(leeway_seconds=0)
    assert record.is_expired(leeway_seconds=10)


@pytest.mark.asyncio
async def test_in_memory_token_store_round_trip():
    store = InMemoryTokenStore()
    key = TokenStoreKey(
        user_key="provider:subject",
        resource="https://example.com",
        authorization_server="https://auth.example.com",
        scope_fingerprint="scope",
    )
    record = TokenRecord(access_token="abc123")

    await store.set(key, record)
    fetched = await store.get(key)
    assert fetched.access_token == record.access_token
    await store.delete(key)
    assert await store.get(key) is None


def test_select_authorization_server_prefers_explicit():
    metadata = ProtectedResourceMetadata(
        resource="https://example.com",
        authorization_servers=[
            "https://auth1.example.com",
            "https://auth2.example.com",
        ],
    )
    # URLs get normalized with trailing slashes by pydantic
    assert (
        select_authorization_server(metadata, "https://auth2.example.com/")
        == "https://auth2.example.com/"
    )
    assert (
        select_authorization_server(metadata, "https://unknown.example.com")
        == "https://auth1.example.com/"  # Falls back to first, which gets normalized
    )


def test_select_authorization_server_with_serialized_config():
    """Test that authorization server selection works after config json serialization.

    When MCPOAuthClientSettings is dumped with mode='json', the authorization_server
    AnyHttpUrl field gets a trailing slash. This test ensures select_authorization_server
    handles this correctly.
    """
    from mcp_agent.config import MCPOAuthClientSettings

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        authorization_server="https://auth.example.com",
        resource="https://api.example.com",
        client_id="test_client",
    )

    dumped_config = oauth_config.model_dump(mode="json")
    reloaded_config = MCPOAuthClientSettings(**dumped_config)

    metadata = ProtectedResourceMetadata(
        resource="https://api.example.com",
        authorization_servers=[
            "https://auth.example.com",
            "https://other-auth.example.com",
        ],
    )

    dumped_metadata = metadata.model_dump(mode="json")
    reloaded_metadata = ProtectedResourceMetadata(**dumped_metadata)

    preferred = str(reloaded_config.authorization_server)
    selected = select_authorization_server(reloaded_metadata, preferred)

    assert selected.rstrip("/") == "https://auth.example.com"


def test_select_authorization_server_trailing_slash_mismatch():
    """Test trailing slash handling in select_authorization_server with various combinations."""
    # Test case 1: preferred has trailing slash, candidates don't
    metadata1 = ProtectedResourceMetadata(
        resource="https://api.example.com",
        authorization_servers=["https://auth.example.com", "https://other.example.com"],
    )

    selected1 = select_authorization_server(metadata1, "https://auth.example.com/")
    assert selected1.rstrip("/") == "https://auth.example.com"

    # Test case 2: preferred doesn't have trailing slash, candidates do
    metadata2 = ProtectedResourceMetadata(
        resource="https://api.example.com",
        authorization_servers=[
            "https://auth.example.com/",
            "https://other.example.com/",
        ],
    )
    selected2 = select_authorization_server(metadata2, "https://auth.example.com")
    assert selected2.rstrip("/") == "https://auth.example.com"


def test_normalize_resource_with_fallback():
    assert (
        normalize_resource("https://example.com/api", None) == "https://example.com/api"
    )
    assert (
        normalize_resource(None, "https://fallback.example.com")
        == "https://fallback.example.com"
    )
    with pytest.raises(ValueError):
        normalize_resource(None, None)


def test_normalize_resource_canonicalizes_case():
    assert normalize_resource("https://Example.COM/", None) == "https://example.com"


def test_oauth_loopback_ports_config_defaults():
    from mcp_agent.config import OAuthSettings

    s = OAuthSettings()
    assert isinstance(s.loopback_ports, list)
    assert 33418 in s.loopback_ports


def test_oauth_callback_base_url_with_serialized_config():
    """Test that callback_base_url works correctly after json serialization.

    When OAuthSettings is dumped with mode='json', the callback_base_url AnyHttpUrl
    field gets a trailing slash.
    """
    from mcp_agent.config import OAuthSettings

    settings = OAuthSettings(callback_base_url="https://callback.example.com")
    dumped = settings.model_dump(mode="json")
    reloaded = OAuthSettings(**dumped)

    flow_id = "test_flow_123"
    if reloaded.callback_base_url:
        constructed_url = f"{str(reloaded.callback_base_url).rstrip('/')}/internal/oauth/callback/{flow_id}"

        assert "//" not in constructed_url.replace("https://", "")
        assert constructed_url.endswith(flow_id)
        assert constructed_url.startswith("https://callback.example.com/")


@pytest.mark.asyncio
async def test_callback_registry_state_mapping():
    from mcp_agent.oauth.callbacks import OAuthCallbackRegistry

    reg = OAuthCallbackRegistry()
    fut = await reg.create_handle("flow1")
    await reg.register_state("flow1", "state1")
    delivered = await reg.deliver_by_state("state1", {"code": "abc"})
    assert delivered is True
    result = await asyncio.wait_for(fut, timeout=0.2)
    assert result["code"] == "abc"


@pytest.mark.asyncio
async def test_authorization_url_construction_with_trailing_slash():
    """Test that authorization URL is constructed correctly when endpoint has trailing slash."""
    from mcp_agent.oauth.flow import AuthorizationFlowCoordinator
    from mcp_agent.config import OAuthSettings, MCPOAuthClientSettings
    from mcp_agent.core.context import Context
    from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata
    from unittest.mock import MagicMock, patch
    import httpx

    oauth_settings = OAuthSettings()
    context = MagicMock(spec=Context)
    from mcp_agent.oauth.identity import OAuthUserIdentity

    user = OAuthUserIdentity(subject="user123", provider="test")

    oauth_config = MCPOAuthClientSettings(
        enabled=True,
        client_id="test_client",
        authorization_server="https://auth.example.com",
        resource="https://api.example.com",
    )

    resource_metadata = ProtectedResourceMetadata(
        resource="https://api.example.com/",
        authorization_servers=["https://auth.example.com/"],
    )

    auth_metadata = OAuthMetadata(
        issuer="https://auth.example.com/",
        authorization_endpoint="https://auth.example.com/authorize/",
        token_endpoint="https://auth.example.com/token/",
    )

    http_client = httpx.AsyncClient()
    flow = AuthorizationFlowCoordinator(
        http_client=http_client, settings=oauth_settings
    )

    captured_payload: Dict[str, Any] | None = None

    async def mock_send_auth_request(_ctx, payload: Dict[str, Any]):
        nonlocal captured_payload
        captured_payload = payload
        # Simulate user declining to test the flow without needing real callback
        raise ConnectionAbortedError("test_exception")

    with patch(
        "mcp_agent.oauth.flow._send_auth_request", side_effect=mock_send_auth_request
    ):
        try:
            await flow.authorize(
                context=context,
                user=user,
                server_name="test_server",
                oauth_config=oauth_config,
                resource="https://api.example.com",
                authorization_server_url="https://auth.example.com",
                resource_metadata=resource_metadata,
                auth_metadata=auth_metadata,
                scopes=["read"],
            )
        except ConnectionAbortedError:
            pass  # Expected to fail due to mock

    await http_client.aclose()
    assert captured_payload is not None, "captured_payload should have been set by mock"

    # Type narrowing for Pylint
    if captured_payload is not None:
        url = captured_payload["url"]
        assert "authorize/?" not in url
        assert "authorize?" in url
        assert url.startswith("https://auth.example.com/authorize?")
