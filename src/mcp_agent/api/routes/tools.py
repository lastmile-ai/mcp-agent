"""Public API endpoints for the tools registry."""

from __future__ import annotations

import uuid
from typing import Iterable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.logging.logger import get_logger

from ...registry.models import ToolItem
from ...registry.store import (
    ToolRegistryMisconfigured,
    ToolRegistryUnavailable,
    store,
)


logger = get_logger(__name__)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def _filter_items(
    items: Iterable[ToolItem],
    *,
    alive: bool | None,
    capabilities: list[str],
    tags: list[str],
    query: str | None,
) -> list[ToolItem]:
    filtered: list[ToolItem] = []
    q = query.lower().strip() if query else None
    for item in items:
        if alive is not None and item.alive is not alive:
            continue
        if capabilities and not all(cap in item.capabilities for cap in capabilities):
            continue
        if tags and not all(tag in item.tags for tag in tags):
            continue
        if q and q not in item.name.lower() and q not in item.id.lower():
            continue
        filtered.append(item)
    return filtered


async def get_tools(request: Request) -> JSONResponse:
    try:
        await store.ensure_started()
        snapshot = await store.get_snapshot()
    except ToolRegistryMisconfigured as exc:
        logger.error("tools.registry.misconfigured", error=str(exc))
        return JSONResponse({"error": "registry_misconfigured"}, status_code=424)
    except ToolRegistryUnavailable:
        logger.warning("tools.registry.unavailable")
        return JSONResponse({"error": "registry_unavailable"}, status_code=503)

    params = request.query_params
    alive = _parse_bool(params.get("alive"))
    capabilities = [value for value in params.getlist("capability") if value]
    tags = [value for value in params.getlist("tag") if value]
    query = params.get("q")

    items = _filter_items(
        snapshot.items,
        alive=alive,
        capabilities=capabilities,
        tags=tags,
        query=query,
    )
    response_model = snapshot.with_items(items)
    trace_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("X-Trace-Id")
        or getattr(request.state, "trace_id", None)
        or request.scope.get("trace_id")
        or str(uuid.uuid4())
    )

    payload = response_model.model_dump(mode="json")
    response = JSONResponse(payload)
    response.headers["ETag"] = f"W/\"{response_model.registry_hash}\""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Trace-Id"] = trace_id
    if store.misconfigured and not snapshot.items:
        response.status_code = 424
    elif not store.ever_succeeded and not snapshot.items:
        response.status_code = 503
    return response


routes = [Route("/tools", get_tools, methods=["GET"])]
router = Router(routes=routes)


def add_tools_api(app):
    """Mount the tools API under /v1."""

    if isinstance(app.router, Router):
        app.router.mount("/v1", router)
    else:
        app.mount("/v1", router)

