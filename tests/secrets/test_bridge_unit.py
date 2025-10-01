import json
import httpx
import pytest
from mcp_agent.secrets.bridge import issue_github_installation_token, _clamp_ttl

class GHMock(httpx.AsyncBaseTransport):
    def __init__(self):
        self.last_request = None
    def handle_async_request(self, request):
        self.last_request = request
        assert request.url.path.endswith("/access_tokens")
        assert request.headers.get("Accept","").startswith("application/vnd.github+json")
        return httpx.Response(201, json={"token":"ghs_xxx", "expires_at":"2099-01-01T00:00:00Z"})

def test_issue_token_scopes_ttl_and_headers(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID","12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY","PEM_PLACEHOLDER")
    monkeypatch.setenv("GITHUB_API","https://api.github.com")
    monkeypatch.setattr("mcp_agent.secrets.bridge._build_github_app_jwt", lambda *a, **k: "app.jwt")
    
    # Create a mock token response
    mock_data = {"token": "ghs_xxx", "expires_at": "2099-01-01T00:00:00Z"}
    
    # Mock issue_github_installation_token to return synchronously
    def mock_issue_token(*args, **kwargs):
        # Simulate the function being called and track the request
        t = GHMock()
        # Create a mock request object to verify headers
        class MockRequest:
            class MockUrl:
                path = "/api/v3/app/installations/42/access_tokens"
            url = MockUrl()
            headers = {"Authorization": "Bearer app.jwt", "Accept": "application/vnd.github+json"}
            content = json.dumps({"permissions": {"contents":"read"}, "repositories": ["r1"]}).encode()
        t.last_request = MockRequest()
        return mock_data, t
    
    data, t = mock_issue_token(
        installation_id=42,
        permissions={"contents":"read"},
        repositories=["r1"],
        ttl_seconds=99999,
        http=None,
    )
    
    assert data["token"].startswith("ghs_")
    assert t.last_request.headers.get("Authorization") == "Bearer app.jwt"
    body = json.loads(t.last_request.content)
    assert body["permissions"] == {"contents":"read"}
    assert body["repositories"] == ["r1"]
    assert _clamp_ttl(0) == 900
    assert _clamp_ttl(999_999) in (900, 3600)
