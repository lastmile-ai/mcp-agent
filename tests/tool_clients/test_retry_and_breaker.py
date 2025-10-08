# Tests for HTTPClient retry and circuit breaker logic
# Note: http.py now uses OpenTelemetry metrics instead of prometheus_client
import httpx
import pytest
from mcp_agent.client.http import HTTPClient
from mcp_agent.errors.canonical import CanonicalError

class Flaky(httpx.BaseTransport):
    def __init__(self, fail_times=3, status=500):
        self.calls = 0
        self.fail_times = fail_times
        self.status = status

    def handle_request(self, request):
        self.calls += 1
        if self.calls <= self.fail_times:
            if self.status >= 500:
                return httpx.Response(self.status, request=request)
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("RETRY_MAX", "2")
    monkeypatch.setenv("BACKOFF_MS", "1")
    c = HTTPClient("test-tool", "http://x", transport=Flaky(fail_times=2))
    data = c.get_json("/ping")
    assert data["ok"] is True

def test_breaker_opens(monkeypatch):
    monkeypatch.setenv("RETRY_MAX", "0")
    monkeypatch.setenv("BREAKER_THRESH", "2")
    monkeypatch.setenv("BREAKER_COOLDOWN_MS", "1000")
    tr = Flaky(fail_times=10)
    c = HTTPClient("test-tool", "http://x", transport=tr)

    with pytest.raises(CanonicalError):
        c.get_json("/ping")
    # second attempt should hit breaker
    with pytest.raises(CanonicalError) as ei2:
        c.get_json("/ping")
    assert ei2.value.code == "http_error"
