"""Tests for the administrative API routers with lifecycle-safe stubs."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.registry.agent import agent_registry
from mcp_agent.registry.loader import build_response
from mcp_agent.registry.models import ToolItem
from mcp_agent.registry.tool import ToolRuntimeRegistry
from mcp_agent.workflows.composer import workflow_composer


class _StubToolRuntime(ToolRuntimeRegistry):
    """Runtime registry replacement that mirrors async locking behaviour."""

    def __init__(self) -> None:
        super().__init__()
        self.reload_count = 0
        self._closed = False

    async def reload(self) -> None:
        self.reload_count += 1
        await super().reload()

    async def list_tools(self):
        if self._closed:
            raise RuntimeError("runtime closed")
        return await super().list_tools()

    async def set_enabled(self, tool_id: str, enabled: bool) -> None:
        if self._closed:
            raise RuntimeError("runtime closed")
        await super().set_enabled(tool_id, enabled)

    async def assign(self, agent_id: str, tool_ids):
        if self._closed:
            raise RuntimeError("runtime closed")
        return await super().assign(agent_id, tool_ids)

    async def aclose(self) -> None:
        async with self._lock:
            self._overrides.clear()
            self._closed = True


class _StubStore:
    """Snapshot store stub that preserves async lifecycle semantics."""

    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.ensure_calls = 0
        self.refresh_calls = 0
        self._lock = asyncio.Lock()
        self._started = asyncio.Event()
        self._stopped = asyncio.Event()

    async def ensure_started(self):
        if self._stopped.is_set():
            raise RuntimeError("store stopped")
        self.ensure_calls += 1
        self._started.set()

    async def get_snapshot(self):
        await self.ensure_started()
        async with self._lock:
            return self._snapshot

    async def refresh(self, force: bool = False):
        await self.ensure_started()
        self.refresh_calls += 1
        async with self._lock:
            return self._snapshot

    async def stop(self):
        async with self._lock:
            self._stopped.set()
            self._started.clear()


def _tool_item(tool_id: str) -> ToolItem:
    return ToolItem(
        id=tool_id,
        name=tool_id.title(),
        version="1.0.0",
        base_url=f"http://{tool_id}",
        alive=True,
        latency_ms=0.1,
        capabilities=["demo"],
        tags=["demo"],
        last_checked_ts=datetime.now(timezone.utc),
        failure_reason=None,
        consecutive_failures=0,
    )


@contextmanager
def _admin_client(monkeypatch, *, include_tools: bool = False):
    from starlette.routing import Route, Router
    from mcp_agent.api.routes.agent import router as agent_router
    from mcp_agent.api.routes.workflow_builder import router as workflow_router
    from mcp_agent.api.routes.tool_registry import router as tools_router

    app = Starlette()
    admin_router = Router()

    def _clone(route):
        if isinstance(route, Route):
            return Route(route.path, route.endpoint, methods=list(route.methods or []))
        return route

    for route in agent_router.routes:
        admin_router.routes.append(_clone(route))
    for route in workflow_router.routes:
        admin_router.routes.append(_clone(route))

    runtime = None
    store = None
    if include_tools:
        snapshot = build_response([_tool_item("alpha")])
        runtime = _StubToolRuntime()
        store = _StubStore(snapshot)
        monkeypatch.setattr("mcp_agent.registry.tool.store", store)
        monkeypatch.setattr("mcp_agent.api.routes.tool_registry.store", store)
        monkeypatch.setattr("mcp_agent.registry.tool.runtime_tool_registry", runtime)
        monkeypatch.setattr("mcp_agent.api.routes.tool_registry.runtime_tool_registry", runtime)
        for route in tools_router.routes:
            admin_router.routes.append(_clone(route))

    app.router.mount("/admin", admin_router)
    client = TestClient(app)

    asyncio.run(agent_registry.clear())
    asyncio.run(workflow_composer.clear())

    try:
        yield client, runtime, store
    finally:
        client.close()
        asyncio.run(agent_registry.clear())
        asyncio.run(workflow_composer.clear())
        if runtime is not None:
            asyncio.run(runtime.aclose())
        if store is not None:
            asyncio.run(store.stop())


def test_admin_client_lifecycle(monkeypatch):
    with _admin_client(monkeypatch) as (client, _, _):
        response = client.get("/admin/agents")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0


def test_agent_crud(monkeypatch):
    with _admin_client(monkeypatch) as (client, _, _):
        create_resp = client.post(
            "/admin/agents",
            json={
                "name": "dev",
                "instruction": "Do work",
                "server_names": ["fs"],
                "metadata": {"owner": "ops"},
                "tags": ["demo"],
            },
        )
        assert create_resp.status_code == 201

        list_resp = client.get("/admin/agents")
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["total"] == 1
        agent_id = body["items"][0]["id"]

        patch_resp = client.patch(
            f"/admin/agents/{agent_id}", json={"instruction": "updated"}
        )
        assert patch_resp.status_code == 200

        delete_resp = client.delete(f"/admin/agents/{agent_id}")
        assert delete_resp.status_code == 204


def test_workflow_builder(monkeypatch):
    with _admin_client(monkeypatch) as (client, _, _):
        create = client.post(
            "/admin/workflows",
            json={
                "id": "wf",
                "name": "Workflow",
                "root": {
                    "id": "root",
                    "kind": "router",
                    "children": [],
                    "config": {},
                },
            },
        )
        assert create.status_code == 201

        step_add = client.post(
            "/admin/workflows/wf/steps",
            json={
                "parent_id": "root",
                "step": {"id": "child", "kind": "task", "config": {}},
            },
        )
        assert step_add.status_code == 200

        detail = client.get("/admin/workflows/wf")
        assert detail.status_code == 200
        assert any(step["id"] == "child" for step in detail.json()["root"]["children"])


def test_tool_registry(monkeypatch):
    with _admin_client(monkeypatch, include_tools=True) as (client, runtime, store):
        resp = client.get("/admin/tools")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

        patch = client.patch(
            "/admin/tools", json={"tool_id": "alpha", "enabled": False}
        )
        assert patch.status_code == 200

        assign = client.post(
            "/admin/tools/assign/dev",
            json={"tool_ids": ["alpha"]},
        )
        assert assign.status_code == 200

        reload = client.post("/admin/tools/reload")
        assert reload.status_code == 200
        assert runtime is not None and runtime.reload_count == 1
        assert store is not None and store.refresh_calls == 1

