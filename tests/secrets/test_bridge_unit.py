import json
import httpx
import pytest

from mcp_agent.secrets.bridge import issue_github_installation_token, _clamp_ttl, _build_github_app_jwt

class GHMock(httpx.AsyncBaseTransport):
    def __init__(self):
        self.last_request = None

    def handle_async_request(self, request):
        self.last_request = request
        assert request.url.path.endswith("/access_tokens")
        assert request.headers.get("Accept","").startswith("application/vnd.github+json")
        # Return a fake token
        return httpx.Response(201, json={"token":"ghs_xxx", "expires_at":"2099-01-01T00:00:00Z"})

@pytest.mark.asyncio
async def test_issue_token_scopes_ttl_and_headers(monkeypatch):
    # Avoid real RSA signing by stubbing the JWT builder
    monkeypatch.setenv("GITHUB_APP_ID","12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY","PEM_PLACEHOLDER")
    monkeypatch.setenv("GITHUB_API","https://api.github.com")
    monkeypatch.setattr("mcp_agent.secrets.bridge._build_github_app_jwt", lambda *a, **k: "app.jwt")
    t = GHMock()
    client = httpx.AsyncClient(transport=t)
    data = await issue_github_installation_token(
        installation_id=42,
        permissions={"contents":"read"},
        repositories=["r1"],
        ttl_seconds=99999,
        http=client,
    )
    assert data["token"].startswith("ghs_")
    # headers carried the app JWT
    assert t.last_request.headers.get("Authorization") == "Bearer app.jwt"
    # body included permissions and repositories
    body = json.loads(t.last_request.content)
    assert body["permissions"] == {"contents":"read"}
    assert body["repositories"] == ["r1"]
    # TTL clamped
    assert _clamp_ttl(0) == 900
    assert _clamp_ttl(999_999) in (900, 3600)
    await client.aclose()
