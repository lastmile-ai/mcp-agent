import httpx
import pytest
from mcp_agent.registry.loader import discover

class OK(httpx.AsyncBaseTransport):
    def __init__(self):
        self.calls = 0
    def handle_async_request(self, request):
        self.calls += 1
        if request.url.path.endswith("/.well-known/mcp"):
            return httpx.Response(200, json={"name":"tool","version":"2.0.0","capabilities":{"search":{}}})
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok":True})
        return httpx.Response(404)

@pytest.mark.asyncio
async def test_discovery_populates_registry_with_retries(monkeypatch):
    # Monkeypatch client creation to use our transport
    import mcp_agent.registry.loader as L
    async def fake_client_ctx():
        return httpx.AsyncClient(transport=OK())
    class Dummy:
        async def __aenter__(self_inner):
            return httpx.AsyncClient(transport=OK())
        async def __aexit__(self_inner, exc_type, exc, tb):
            pass
    monkeypatch.setattr(L.httpx, "AsyncClient", lambda *a, **k: Dummy())
    entries = [{"name":"t1","base_url":"http://tool1:123"}]
    out = await discover(entries, retries=1, backoff_ms=1)
    assert out and out[0]["alive"] is True
    assert out[0]["well_known"] is True
    assert out[0]["capabilities"].get("search") == {}
