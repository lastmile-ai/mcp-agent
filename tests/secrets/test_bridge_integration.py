import httpx
import pytest

from mcp_agent.secrets.bridge import mount_github_token_for_run

class GHMock(httpx.AsyncBaseTransport):
    def handle_async_request(self, request):
        return httpx.Response(201, json={"token":"ghs_mocktoken", "expires_at":"2099-01-01T00:00:00Z"})

@pytest.mark.asyncio
async def test_mount_and_clear(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID","12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY","PEM_PLACEHOLDER")
    monkeypatch.setattr("mcp_agent.secrets.bridge._build_github_app_jwt", lambda *a, **k: "app.jwt")

    async with mount_github_token_for_run(
        target="github-mcp-server",
        installation_id=1,
        permissions={"contents":"read"},
        repositories=["r1"],
        ttl_seconds=60,
    ) as tok:
        h = tok.as_header()
        assert "Authorization" in h and h["Authorization"].startswith("token ")
    # Context exit should run cleanup without raising.
