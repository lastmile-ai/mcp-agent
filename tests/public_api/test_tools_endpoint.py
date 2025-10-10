from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes.tools import add_tools_api
from mcp_agent.registry.loader import build_response
from mcp_agent.registry.models import ToolItem
from mcp_agent.registry.store import (
    ToolRegistryMisconfigured,
    ToolRegistryUnavailable,
)


class StubStore:
    def __init__(self, snapshot, *, misconfigured=None, ever_succeeded=True):
        self._snapshot = snapshot
        self._misconfigured = misconfigured
        self._ever_succeeded = ever_succeeded

    async def ensure_started(self):
        return None

    async def get_snapshot(self):
        if isinstance(self._snapshot, Exception):
            raise self._snapshot
        return self._snapshot

    @property
    def misconfigured(self):
        return self._misconfigured

    @property
    def ever_succeeded(self):
        return self._ever_succeeded


def _item(**kwargs) -> ToolItem:
    defaults = dict(
        id="alpha",
        name="Alpha",
        version="1.0.0",
        base_url="http://alpha",
        alive=True,
        latency_ms=12.3,
        capabilities=["tools.list"],
        tags=["demo"],
        last_checked_ts=datetime.now(timezone.utc),
        failure_reason=None,
        consecutive_failures=0,
    )
    defaults.update(kwargs)
    return ToolItem(**defaults)


def test_get_tools_filters_and_headers(monkeypatch):
    snapshot = build_response(
        [
            _item(id="alpha", name="Alpha", tags=["demo", "internal"], capabilities=["tools.list", "tools.call"]),
            _item(id="beta", name="Beta", alive=False, tags=["external"], capabilities=["tools.search"]),
        ]
    )
    stub_store = StubStore(snapshot)
    monkeypatch.setattr("mcp_agent.api.routes.tools.store", stub_store)

    app = Starlette()
    add_tools_api(app)
    client = TestClient(app)

    response = client.get(
        "/v1/tools",
        params={"alive": "true", "capability": "tools.call", "tag": "internal", "q": "alp"},
        headers={"X-Trace-Id": "trace-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] and body["items"][0]["id"] == "alpha"
    assert response.headers["ETag"].startswith("W/\"sha256-")
    assert response.headers["X-Trace-Id"] == "trace-123"


def test_get_tools_misconfigured_returns_424(monkeypatch):
    stub_store = StubStore(ToolRegistryMisconfigured("missing"), misconfigured=Exception("missing"))
    monkeypatch.setattr("mcp_agent.api.routes.tools.store", stub_store)
    app = Starlette()
    add_tools_api(app)
    client = TestClient(app)
    response = client.get("/v1/tools")
    assert response.status_code == 424


def test_get_tools_unavailable_returns_503(monkeypatch):
    stub_store = StubStore(ToolRegistryUnavailable("empty"), ever_succeeded=False)
    monkeypatch.setattr("mcp_agent.api.routes.tools.store", stub_store)
    app = Starlette()
    add_tools_api(app)
    client = TestClient(app)
    response = client.get("/v1/tools")
    assert response.status_code == 503
