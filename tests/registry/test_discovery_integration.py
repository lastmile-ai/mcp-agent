import httpx
import pytest
from mcp_agent.registry.loader import discover


class OK(httpx.AsyncBaseTransport):
    def __init__(self):
        self.calls = 0

    async def handle_async_request(self, request):
        self.calls += 1
        if request.url.path.endswith("/.well-known/mcp"):
            return httpx.Response(200, json={"name": "tool", "version": "2.0.0", "capabilities": {"search": {}}})
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)


@pytest.mark.asyncio
async def test_discovery_populates_registry_with_retries(monkeypatch):
    # Monkeypatch client creation to use our transport
    import mcp_agent.registry.loader as L

    # Create the transport instance that will be reused
    ok_transport = OK()

    # Save reference to the original AsyncClient before monkeypatching
    OriginalAsyncClient = httpx.AsyncClient

    class DummyAsyncClient:
        """Mock AsyncClient that uses OK transport and works as a context manager."""

        def __init__(self, *args, **kwargs):
            # Use the original httpx.AsyncClient class (before monkeypatching)
            # to avoid infinite recursion
            self._real_client = OriginalAsyncClient(transport=ok_transport)

        async def __aenter__(self):
            # Return the real client when entering the context
            await self._real_client.__aenter__()
            return self._real_client

        async def __aexit__(self, exc_type, exc, tb):
            # Properly exit the real client context
            await self._real_client.__aexit__(exc_type, exc, tb)

    # Patch httpx.AsyncClient in the loader module
    monkeypatch.setattr(L.httpx, "AsyncClient", DummyAsyncClient)

    entries = [{"name": "t1", "base_url": "http://tool1:123"}]
    out = await discover(entries)

    assert out and out[0]["alive"] is True
    assert out[0]["well_known"] is True
    assert out[0]["capabilities"].get("search") == {}
