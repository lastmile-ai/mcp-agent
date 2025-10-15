"""Agent registry administration routes."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, Router

from mcp_agent.models.agent import AgentSpecListResponse, AgentSpecPatch, AgentSpecPayload
from mcp_agent.registry.agent import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    agent_registry,
)


async def list_agents(_request: Request) -> JSONResponse:
    items = await agent_registry.list()
    response = AgentSpecListResponse(items=items, total=len(items))
    return JSONResponse(response.model_dump(mode="json"))


async def create_agent(request: Request) -> JSONResponse:
    payload = AgentSpecPayload(**(await request.json()))
    try:
        envelope = await agent_registry.create(payload)
    except AgentAlreadyExistsError:
        return JSONResponse({"error": "exists"}, status_code=409)
    return JSONResponse(envelope.model_dump(mode="json"), status_code=201)


async def get_agent(request: Request) -> JSONResponse:
    agent_id = request.path_params["agent_id"]
    try:
        envelope = await agent_registry.get(agent_id)
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(envelope.model_dump(mode="json"))


async def patch_agent(request: Request) -> JSONResponse:
    agent_id = request.path_params["agent_id"]
    patch = AgentSpecPatch(**(await request.json()))
    try:
        envelope = await agent_registry.update(agent_id, patch)
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    except AgentAlreadyExistsError:
        return JSONResponse({"error": "conflict"}, status_code=409)
    return JSONResponse(envelope.model_dump(mode="json"))


async def delete_agent(request: Request) -> JSONResponse:
    agent_id = request.path_params["agent_id"]
    try:
        await agent_registry.delete(agent_id)
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({}, status_code=204)


async def download_agents(_request: Request) -> PlainTextResponse:
    yaml_text = await agent_registry.export_yaml()
    return PlainTextResponse(yaml_text, media_type="text/yaml")


async def upload_agents(request: Request) -> JSONResponse:
    text = await request.body()
    try:
        items = await agent_registry.import_yaml(text.decode("utf-8"), replace=True)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(
        {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}
    )


routes = [
    Route("/agents", list_agents, methods=["GET"]),
    Route("/agents", create_agent, methods=["POST"]),
    Route("/agents/{agent_id}", get_agent, methods=["GET"]),
    Route("/agents/{agent_id}", patch_agent, methods=["PATCH"]),
    Route("/agents/{agent_id}", delete_agent, methods=["DELETE"]),
    Route("/agents/download", download_agents, methods=["GET"]),
    Route("/agents/upload", upload_agents, methods=["POST"]),
]

router = Router(routes=routes)


def add_agent_api(app, prefix: str = "/v1/admin") -> None:
    if isinstance(app.router, Router):
        app.router.mount(prefix, router)
    else:  # pragma: no cover - Starlette compatibility
        app.mount(prefix, router)


__all__ = ["add_agent_api", "router"]
