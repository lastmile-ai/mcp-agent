import os
import json
import hmac
import hashlib
import pytest
import pytest_asyncio
import httpx
from types import SimpleNamespace

from mcp_agent.config import Settings, MCPServerSettings
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.integrations.github_sentinel import register_github_preinit

class _RespOnceClient:
    def __init__(self, status=200, json_body=None):
        self.status = status
        self.json_body = json_body or {"token": "t"}
        self.calls = 0
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False
    async def post(self, url, headers=None, content=None):
        self.calls += 1
        return httpx.Response(self.status, json=self.json_body)

@pytest_asyncio.fixture
async def registry_and_cfg():
    return ServerRegistry(config=Settings()), Settings()

@pytest.mark.asyncio
async def test_skips_when_missing_sentinel_url(monkeypatch, registry_and_cfg):
    reg, cfg = registry_and_cfg
    # prevent any HTTP usage if misconfigured
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP should not be called")))
    os.environ.pop("SENTINEL_URL", None)
    os.environ.pop("SENTINEL_HMAC_KEY", None)
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)
    assert conf.env.get("GITHUB_TOKEN") is None

@pytest.mark.asyncio
async def test_skips_when_missing_hmac(monkeypatch, registry_and_cfg):
    reg, cfg = registry_and_cfg
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP should not be called")))
    os.environ["SENTINEL_URL"] = "https://sentinel.local"
    os.environ.pop("SENTINEL_HMAC_KEY", None)
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)
    assert conf.env.get("GITHUB_TOKEN") is None

@pytest.mark.asyncio
async def test_streamable_http_and_websocket_headers(monkeypatch, registry_and_cfg):
    reg, cfg = registry_and_cfg
    client = _RespOnceClient(status=200, json_body={"token": "z"})
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: client)
    os.environ["SENTINEL_URL"] = "https://sentinel.local"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    for transport in ("streamable_http", "websocket"):
        conf = MCPServerSettings(name="github", transport=transport, headers={"X": "1"}, env={"GITHUB_ALLOWED_REPO": "owner/name"})
        await hook("github", conf, None)
        assert conf.headers.get("Authorization") == "Bearer z"
        assert conf.headers.get("X") == "1"

@pytest.mark.asyncio
async def test_http_error_raises(monkeypatch, registry_and_cfg):
    reg, cfg = registry_and_cfg
    client = _RespOnceClient(status=403, json_body={"err":"deny"})
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: client)
    os.environ["SENTINEL_URL"] = "https://sentinel.local"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    with pytest.raises(httpx.HTTPStatusError):
        await hook("github", conf, None)

@pytest.mark.asyncio
async def test_missing_token_raises(monkeypatch, registry_and_cfg):
    reg, cfg = registry_and_cfg
    client = _RespOnceClient(status=200, json_body={"expires_at":"x"})
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: client)
    os.environ["SENTINEL_URL"] = "https://sentinel.local"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    with pytest.raises(RuntimeError):
        await hook("github", conf, None)

@pytest.mark.asyncio
async def test_no_disk_writes(tmp_path, monkeypatch, registry_and_cfg, cwd_tmpdir=None):
    # Snapshot CWD entries before
    before = set(os.listdir(tmp_path))
    reg, cfg = registry_and_cfg
    client = _RespOnceClient(status=200, json_body={"token":"ok"})
    monkeypatch.setattr("mcp_agent.integrations.github_sentinel.httpx.AsyncClient", lambda *a, **k: client)
    os.environ["SENTINEL_URL"] = "https://sentinel.local"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"
    register_github_preinit(reg, cfg)
    hook = reg.pre_init_hooks["github"]
    conf = MCPServerSettings(name="github", transport="stdio", env={"GITHUB_ALLOWED_REPO": "owner/name"})
    await hook("github", conf, None)
    after = set(os.listdir(tmp_path))
    assert before == after
