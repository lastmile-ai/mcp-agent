import asyncio
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.registry.agent import agent_registry
from mcp_agent.registry.loader import build_response
from mcp_agent.registry.models import ToolItem
from mcp_agent.workflows.composer import workflow_composer


class _StubToolRuntime:
    def __init__(self, tools):
        self.tools = tools
        self.enabled: dict[str, bool] = {}
        self.assignments: dict[str, list[str]] = {}
        self.reload_count = 0

    async def list_tools(self):
        return self.tools

    async def get_assignments(self):
        return self.assignments

    async def get_status_map(self):
        return self.enabled

    async def set_enabled(self, tool_id: str, enabled: bool):
        self.enabled[tool_id] = enabled

    async def assign(self, agent_id: str, tool_ids):
        updated: dict[str, list[str]] = {}
        for tool_id in tool_ids:
            agents = self.assignments.setdefault(tool_id, [])
            if agent_id not in agents:
                agents.append(agent_id)
            updated[tool_id] = sorted(agents)
        return updated

    async def reload(self):
        self.reload_count += 1


class _StubStore:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.ensure_calls = 0

    async def ensure_started(self):
        self.ensure_calls += 1

    async def get_snapshot(self):
        return self._snapshot


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


def _setup_app(monkeypatch, *, include_tools: bool = False):
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
    if include_tools:
        snapshot = build_response([_tool_item("alpha")])
        stub_runtime = _StubToolRuntime(snapshot.items)
        stub_store = _StubStore(snapshot)
        monkeypatch.setattr(
            "mcp_agent.api.routes.tool_registry.runtime_tool_registry", stub_runtime
        )
        monkeypatch.setattr("mcp_agent.api.routes.tool_registry.store", stub_store)
        for route in tools_router.routes:
            admin_router.routes.append(_clone(route))
    app.router.mount("/admin", admin_router)
    return TestClient(app)
def test_agent_crud(monkeypatch):
    asyncio.run(agent_registry.clear())
    client = _setup_app(monkeypatch)
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

    patch_resp = client.patch(f"/admin/agents/{agent_id}", json={"instruction": "updated"})
    assert patch_resp.status_code == 200
    delete_resp = client.delete(f"/admin/agents/{agent_id}")
    assert delete_resp.status_code == 204


def test_workflow_builder(monkeypatch):
    asyncio.run(workflow_composer.clear())
    client = _setup_app(monkeypatch)
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
    client = _setup_app(monkeypatch, include_tools=True)
    resp = client.get("/admin/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    patch = client.patch("/admin/tools", json={"tool_id": "alpha", "enabled": False})
    assert patch.status_code == 200
    assign = client.post(
        "/admin/tools/assign/dev",
        json={"tool_ids": ["alpha"]},
    )
    assert assign.status_code == 200
    reload = client.post("/admin/tools/reload")
    assert reload.status_code == 200

