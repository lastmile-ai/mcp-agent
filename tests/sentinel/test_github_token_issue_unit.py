import json as _json
import os
import httpx
import pytest
from mcp_agent.sentinel.client import issue_github_token
class FakeAsyncClient:
    def __init__(self):
        self.captured = {}
    async def post(self, url, json=None, headers=None):
        self.captured["url"] = url
        self.captured["json"] = json
        self.captured["headers"] = headers
        # Return a minimal httpx.Response with JSON body
        req = httpx.Request("POST", url)
        body = {"token":"ghs_dummy", "expires_at":"2099-01-01T00:00:00Z", "granted_permissions":{"contents":"read"}}
        return httpx.Response(200, request=req, content=_json.dumps(body).encode())
@pytest.mark.asyncio
async def test_issue_github_token_request_shape(monkeypatch):
    os.environ["SENTINEL_URL"] = "https://sentinel.internal"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    # No allowed guard to start
    monkeypatch.setenv("GITHUB_ALLOWED_REPO", "owner/name")
    # Patch SentinelClient inside module to use FakeAsyncClient
    import mcp_agent.sentinel.client as mod
    fake = FakeAsyncClient()
    # Patch client construction to inject our fake http
    real_cls = mod.SentinelClient
    def fake_init(self, base_url, signing_key, http=None):
        self.base_url = base_url.rstrip("/")
        self.signing_key = signing_key.encode("utf-8")
        self.http = fake
    monkeypatch.setattr(real_cls, "__init__", fake_init, raising=True)
    # Also provide a jsonlib name used in FakeAsyncClient
    monkeypatch.setenv("PYTHONHASHSEED","0")
    mod.jsonlib = _json
    data = await issue_github_token(repo="owner/name", ttl_seconds=600)
    assert data["token"] == "ghs_dummy"
    sent = fake.captured["json"]
    assert "repo" in sent and sent["repo"] == "owner/name"
    assert "installation_id" not in sent
    assert sent.get("ttl_seconds") == 600
    # Verify HMAC header present
    sig = fake.captured["headers"].get("X-Signature")
    assert isinstance(sig, str) and len(sig) == 64  # hex sha256
@pytest.mark.asyncio
async def test_issue_github_token_repo_guard(monkeypatch):
    os.environ["SENTINEL_URL"] = "https://sentinel.internal"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    monkeypatch.setenv("GITHUB_ALLOWED_REPO", "owner/name")
    with pytest.raises(ValueError):
        await issue_github_token(repo="other/name")
