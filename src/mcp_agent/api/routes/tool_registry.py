"""Administrative routes for managing the live tool registry."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.registry.store import (
    ToolRegistryMisconfigured,
    ToolRegistryUnavailable,
    store,
)
from mcp_agent.registry.tool import runtime_tool_registry


async def _ensure_registry_started():
    await store.ensure_started()


async def get_tools(_request: Request) -> JSONResponse:
    try:
        await _ensure_registry_started()
        tools = await runtime_tool_registry.list_tools()
        assignments = await runtime_tool_registry.get_assignments()
        status_map = await runtime_tool_registry.get_status_map()
    except ToolRegistryMisconfigured as exc:
        return JSONResponse({"error": str(exc)}, status_code=424)
    except ToolRegistryUnavailable:
        return JSONResponse({"error": "registry_unavailable"}, status_code=503)

    payload = []
    for tool in tools:
        data = tool.model_dump(mode="json")
        data["enabled"] = status_map.get(tool.id, True)
        data["assigned_agents"] = assignments.get(tool.id, [])
        payload.append(data)
    return JSONResponse({"items": payload, "total": len(payload)})


async def patch_tools(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    updates = body if isinstance(body, list) else [body]
    for update in updates:
        tool_id = update.get("tool_id") or update.get("id")
        enabled = update.get("enabled")
        if not isinstance(tool_id, str) or enabled is None:
            return JSONResponse({"error": "invalid_schema"}, status_code=400)
        await runtime_tool_registry.set_enabled(tool_id, bool(enabled))
    return JSONResponse({"updated": len(updates)})


async def assign_tools(request: Request) -> JSONResponse:
    agent_id = request.path_params["agent_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    tool_ids = body.get("tool_ids") if isinstance(body, dict) else None
    if not isinstance(tool_ids, list) or not all(isinstance(tid, str) for tid in tool_ids):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)
    assignments = await runtime_tool_registry.assign(agent_id, tool_ids)
    return JSONResponse({"assignments": assignments})


async def reload_tools(_request: Request) -> JSONResponse:
    await runtime_tool_registry.reload()
    return JSONResponse({"status": "reloading"})


routes = [
    Route("/tools", get_tools, methods=["GET"]),
    Route("/tools", patch_tools, methods=["PATCH"]),
    Route("/tools/reload", reload_tools, methods=["POST"]),
    Route("/tools/assign/{agent_id}", assign_tools, methods=["POST", "PATCH"]),
]

router = Router(routes=routes)


def add_tool_registry_api(app, prefix: str = "/v1/admin") -> None:
    if isinstance(app.router, Router):
        app.router.mount(prefix, router)
    else:  # pragma: no cover - Starlette compatibility
        app.mount(prefix, router)


__all__ = ["add_tool_registry_api", "router"]
