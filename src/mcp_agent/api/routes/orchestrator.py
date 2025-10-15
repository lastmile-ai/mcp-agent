"""Routes exposing orchestrator runtime state."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.models.orchestrator import (
    OrchestratorPlan,
    OrchestratorQueueItem,
    OrchestratorStatePatch,
)
from mcp_agent.orchestrator.runtime import orchestrator_runtime


async def get_state(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    snapshot = await orchestrator_runtime.get_snapshot(orchestrator_id)
    return JSONResponse(snapshot.state.model_dump(mode="json"))


async def patch_state(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    patch = OrchestratorStatePatch(**(await request.json()))
    state = await orchestrator_runtime.update_state(orchestrator_id, patch)
    return JSONResponse(state.model_dump(mode="json"))


async def get_plan(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    snapshot = await orchestrator_runtime.get_snapshot(orchestrator_id)
    return JSONResponse(snapshot.plan.model_dump(mode="json"))


async def set_plan(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    plan = OrchestratorPlan(**(await request.json()))
    plan = await orchestrator_runtime.set_plan(orchestrator_id, plan)
    return JSONResponse(plan.model_dump(mode="json"))


async def get_queue(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    snapshot = await orchestrator_runtime.get_snapshot(orchestrator_id)
    return JSONResponse([item.model_dump(mode="json") for item in snapshot.queue])


async def set_queue(request: Request) -> JSONResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    payload = await request.json()
    if not isinstance(payload, list):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)
    items = [OrchestratorQueueItem(**item) for item in payload]
    queue_items = await orchestrator_runtime.set_queue(orchestrator_id, items)
    return JSONResponse([item.model_dump(mode="json") for item in queue_items])


async def stream_events(request: Request) -> StreamingResponse:
    orchestrator_id = request.path_params["orchestrator_id"]
    queue = await orchestrator_runtime.subscribe(orchestrator_id)

    async def event_source() -> AsyncIterator[str]:
        try:
            while True:
                event = await queue.get()
                payload = event.model_dump(mode="json")
                yield f"id: {payload['id']}\nevent: {payload['type']}\ndata: {payload}\n\n"
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            pass
        finally:
            await orchestrator_runtime.unsubscribe(orchestrator_id, queue)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


routes = [
    Route("/orchestrators/{orchestrator_id}/state", get_state, methods=["GET"]),
    Route("/orchestrators/{orchestrator_id}/state", patch_state, methods=["PATCH"]),
    Route("/orchestrators/{orchestrator_id}/plan", get_plan, methods=["GET"]),
    Route("/orchestrators/{orchestrator_id}/plan", set_plan, methods=["POST", "PUT"]),
    Route("/orchestrators/{orchestrator_id}/queue", get_queue, methods=["GET"]),
    Route("/orchestrators/{orchestrator_id}/queue", set_queue, methods=["POST", "PUT"]),
    Route("/orchestrators/{orchestrator_id}/events", stream_events, methods=["GET"]),
]

router = Router(routes=routes)


def add_orchestrator_api(app, prefix: str = "/v1/admin") -> None:
    if isinstance(app.router, Router):
        app.router.mount(prefix, router)
    else:  # pragma: no cover - Starlette compatibility
        app.mount(prefix, router)


__all__ = ["add_orchestrator_api", "router"]
