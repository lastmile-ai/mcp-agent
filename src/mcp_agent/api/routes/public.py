import asyncio
import json
import os
import uuid
from typing import Dict, List, Set, Tuple

from mcp_agent.feature.intake import FeatureIntakeManager

import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.controller import RunConfig, RunController
from mcp_agent.runloop.events import BudgetSnapshot, EventBus, build_payload


class PublicAPIState:
    """Encapsulates all mutable state for the public API."""

    def __init__(self):
        self.runs: Dict[str, Dict] = {}
        self.event_buses: Dict[str, EventBus] = {}
        self.tasks: Set[asyncio.Task] = set()
        self.artifacts: Dict[str, tuple[bytes, str]] = {}
        self.feature_manager = FeatureIntakeManager(artifact_sink=self.artifacts)

    async def cancel_all_tasks(self):
        """Cancel all tracked background tasks."""
        tasks = list(self.tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        for bus in list(self.event_buses.values()):
            await bus.close()
        self.event_buses.clear()
        await self.feature_manager.close()
        self.feature_manager.reset()

    def clear(self):
        """Clear all state dictionaries."""
        self.runs.clear()
        self.event_buses.clear()
        self.feature_manager.reset()


def _env_list(name: str) -> List[str]:
    val = os.getenv(name, "")
    return [s.strip() for s in val.split(",") if s.strip()]


def _authenticate(request: Request) -> Tuple[bool, str]:
    api_keys = set(_env_list("STUDIO_API_KEYS"))
    key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if key and key in api_keys:
        return True, "api_key"
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        hs = os.getenv("JWT_HS256_SECRET")
        if hs:
            try:
                jwt.decode(token, hs, algorithms=["HS256"], options={"verify_aud": False})
                return True, "jwt_hs256"
            except Exception:
                pass
        pub = os.getenv("JWT_PUBLIC_KEY_PEM")
        if pub:
            try:
                jwt.decode(token, pub, algorithms=["RS256"], options={"verify_aud": False})
                return True, "jwt_rs256"
            except Exception:
                pass
    return False, "unauthorized"


def _get_state(request: Request) -> PublicAPIState:
    """Get state from request. Raises AttributeError if not injected."""
    return request.state.public_api_state


async def create_run(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    project_id = body.get("project_id")
    run_type = body.get("run_type")
    if not isinstance(project_id, str) or not isinstance(run_type, str):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)

    state = _get_state(request)
    run_id = str(uuid.uuid4())
    trace_id = body.get("trace_id") or str(uuid.uuid4())
    budget_limit = body.get("llm_time_budget_s")
    limit_seconds = float(budget_limit) if isinstance(budget_limit, (int, float)) else None
    budget = LLMBudget(limit_seconds=limit_seconds)
    event_bus = EventBus()
    state.event_buses[run_id] = event_bus

    state.runs[run_id] = {
        "project_id": project_id,
        "run_type": run_type,
        "trace_id": trace_id,
        "status": "running",
    }

    iterations = body.get("iterations")
    try:
        iteration_count = int(iterations)
    except (TypeError, ValueError):
        iteration_count = 1
    iteration_count = max(1, iteration_count)

    config = RunConfig(trace_id=trace_id, iteration_count=iteration_count, pack_hash=body.get("pack_hash"))

    async def _run_controller() -> None:
        controller = RunController(config=config, event_bus=event_bus, llm_budget=budget)
        try:
            await controller.run()
            state.runs[run_id]["status"] = "completed"
        except Exception as exc:  # pragma: no cover - defensive
            state.runs[run_id]["status"] = "failed"
            snapshot = BudgetSnapshot(
                llm_active_ms=budget.active_ms,
                remaining_s=budget.remaining_seconds(),
            )
            await event_bus.publish(
                build_payload(
                    event="aborted",
                    trace_id=trace_id,
                    iteration=0,
                    pack_hash=config.pack_hash,
                    budget=snapshot,
                    violation=True,
                    reason=str(exc),
                )
            )
            await event_bus.close()

    task = asyncio.create_task(_run_controller())
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    return JSONResponse({"id": run_id, "status": "running"}, status_code=202)


async def stream_run(request: Request) -> StreamingResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = _get_state(request)
    event_bus = state.event_buses.get(run_id)
    if event_bus is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def event_source():
        queue = event_bus.subscribe()
        try:
            while True:
                try:
                    data = await queue.get()
                    if data == "__EOF__":
                        break
                    yield f"data: {data}\n\n"
                except asyncio.CancelledError:
                    break
                except Exception:
                    break
        finally:
            event_bus.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


async def cancel_run(request: Request):
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = _get_state(request)
    run = state.runs.get(run_id)
    if not run:
        return JSONResponse({"error": "not_found"}, status_code=404)
    run["status"] = "cancelled"
    bus = state.event_buses.get(run_id)
    if bus is not None:
        snapshot = BudgetSnapshot(llm_active_ms=0, remaining_s=None)
        await bus.publish(
            build_payload(
                event="cancelled",
                trace_id=run.get("trace_id", ""),
                iteration=0,
                pack_hash=None,
                budget=snapshot,
            )
        )
        await bus.close()
    return JSONResponse({"id": run_id, "status": "cancelled"}, status_code=200)


async def get_artifact(request: Request):
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = _get_state(request)
    art_id = request.path_params.get("id", "")
    blob = state.artifacts.get(art_id)
    if not blob:
        return JSONResponse({"error": "not_found"}, status_code=404)
    data, content_type = blob
    try:
        payload = json.loads(data.decode("utf-8"))
        return JSONResponse(payload, media_type=content_type)
    except Exception:
        # Binary fallback
        return JSONResponse({"error": "unsupported_content"}, status_code=415)


routes = [
    Route("/runs", create_run, methods=["POST"]),
    Route("/stream/{id}", stream_run, methods=["GET"]),
    Route("/runs/{id}/cancel", cancel_run, methods=["POST"]),
    Route("/artifacts/{id}", get_artifact, methods=["GET"]),
]

from .feature import router as feature_router

router = Router(routes=routes)
router.mount("/features", feature_router)
