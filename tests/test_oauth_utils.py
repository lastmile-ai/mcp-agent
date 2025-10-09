import time
import pathlib
import sys

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
