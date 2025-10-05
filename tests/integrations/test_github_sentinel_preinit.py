import os
import json
import hmac
import hashlib
import pytest
import pytest_asyncio
import httpx

from mcp_agent.config import Settings, MCPServerSettings
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.integrations.github_sentinel import register_github_preinit

class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self._last = None
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return False
    async def post(self, url, headers=None, content=None):
        # record last call for assertions
        self._last = (url, headers or {}, content)
        return httpx.Response(200, json={
            "token": "ghs_testtoken",
            "expires_at": "2025-01-01T00:00:00Z",
            "granted_permissions": {}
        })

@pytest_asyncio.fixture(autouse=True)
async def clean_env(monkeypatch):
    # Ensure clean env for each test
    for k in ["SENTINEL_URL", "SENTINEL_HMAC_KEY", "GITHUB_ALLOWED_REPO"]:
        monkeypatch.delenv(k, raising=False)
    yield
    for k in ["SENTINEL_URL", "SENTINEL_HMAC_KEY", "GITHUB_ALLOWED_REPO"]:
        monkeypatch.delenv(k, raising=False)

@pytest_asyncio.fixture
async def registry_and_settings():
    cfg = Settings()  # defaults are fine
    reg = ServerRegistry(config=cfg)
    return reg, cfg

@pytest.mark.asyncio
async def test_injects_token_into_env_for_github_stdio(monkeypatch, registry_and_settings):
    reg, cfg = registry_and_settings
    # Patch httpx.AsyncClient constructor to return our fake
    fake = _FakeAsyncClient()
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: fake)
    # Minimal env
    monkeypatch.setenv("SENTINEL_URL", "https://sentinel.local")
    monkeypatch.setenv("SENTINEL_HMAC_KEY", "k")
    monkeypatch.setenv("GITHUB_ALLOWED_REPO", "owner/name")

    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks.get("github")
    assert hook is not None

    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)

    assert "GITHUB_TOKEN" in conf.env
    assert conf.env["GITHUB_TOKEN"] == "ghs_testtoken"
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in conf.env
    assert "GITHUB_ALLOWED_REPO" not in conf.env  # guard removed

@pytest.mark.asyncio
async def test_sets_authorization_header_for_http_transports(monkeypatch, registry_and_settings):
    reg, cfg = registry_and_settings
    fake = _FakeAsyncClient()
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: fake)
    monkeypatch.setenv("SENTINEL_URL", "https://sentinel.local")
    monkeypatch.setenv("SENTINEL_HMAC_KEY", "k")
    monkeypatch.setenv("GITHUB_ALLOWED_REPO", "owner/name")

    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks.get("github")

    conf = MCPServerSettings(name="github", transport="sse", headers={"X-Test": "1"}, env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)

    assert conf.headers is not None
    assert conf.headers.get("Authorization") == "Bearer ghs_testtoken"
    # existing headers preserved
    assert conf.headers.get("X-Test") == "1"

@pytest.mark.asyncio
async def test_skips_without_repo(monkeypatch, registry_and_settings):
    reg, cfg = registry_and_settings
    fake = _FakeAsyncClient()
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: fake)
    monkeypatch.setenv("SENTINEL_URL", "https://sentinel.local")
    monkeypatch.setenv("SENTINEL_HMAC_KEY", "k")
    # no GITHUB_ALLOWED_REPO

    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks.get("github")
    conf = MCPServerSettings(name="github", transport="stdio", env={})
    await hook("github", conf, None)

    assert conf.env == {}

@pytest.mark.asyncio
async def test_hmac_header_and_payload(monkeypatch, registry_and_settings):
    reg, cfg = registry_and_settings
    fake = _FakeAsyncClient()
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: fake)
    monkeypatch.setenv("SENTINEL_URL", "https://sentinel.local")
    monkeypatch.setenv("SENTINEL_HMAC_KEY", "secret123")
    monkeypatch.setenv("GITHUB_ALLOWED_REPO", "owner/name")

    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks.get("github")
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)

    # verify HMAC header
    url, headers, content = fake._last
    assert url.endswith("/v1/github/token")
    assert "X-Sentinel-Signature" in headers
    assert headers["Content-Type"] == "application/json"
    # recompute
    expected = hmac.new(b"secret123", json.dumps({"repo": "owner/name"}, separators=(",", ":"), sort_keys=True).encode("utf-8"), hashlib.sha256).hexdigest()
    assert headers["X-Sentinel-Signature"].startswith("sha256=")
    assert headers["X-Sentinel-Signature"][7:] == expected
