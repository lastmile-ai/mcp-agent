"""Routes for handling human input requests via HTTP/SSE."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.human_input.runtime import human_input_runtime
from mcp_agent.human_input.types import HumanInputResponse


async def list_pending(_request: Request) -> JSONResponse:
    pending = await human_input_runtime.pending()
    return JSONResponse([item.model_dump(mode="json") for item in pending])


async def stream_requests(_request: Request) -> StreamingResponse:
    queue = await human_input_runtime.subscribe()

    async def event_source() -> AsyncIterator[str]:
        try:
            while True:
                request = await queue.get()
                payload = request.model_dump(mode="json")
                yield f"event: request\ndata: {payload}\n\n"
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            pass
        finally:
            await human_input_runtime.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


async def respond(request: Request) -> JSONResponse:
    body = await request.json()
    request_id = body.get("request_id")
    response_text = body.get("response")
    if not isinstance(request_id, str):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)
    response = HumanInputResponse(request_id=request_id, response=response_text or "")
    success = await human_input_runtime.resolve(response)
    if not success:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({"status": "ok"})


routes = [
    Route("/human_input/requests", list_pending, methods=["GET"]),
    Route("/human_input/stream", stream_requests, methods=["GET"], include_in_schema=False),
    Route("/human_input/respond", respond, methods=["POST"]),
]

router = Router(routes=routes)


def add_human_input_api(app, prefix: str = "/v1/admin") -> None:
    if isinstance(app.router, Router):
        app.router.mount(prefix, router)
    else:  # pragma: no cover - Starlette compatibility
        app.mount(prefix, router)


__all__ = ["add_human_input_api", "router"]
