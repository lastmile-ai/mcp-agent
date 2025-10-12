import asyncio
import json
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.runloop.controller import RunConfig, RunController
from mcp_agent.runloop.events import BudgetSnapshot, EventBus, build_payload

from .feature import router as feature_router
from .state import (
    PublicAPIState as _PublicAPIState,
    authenticate_request,
    get_public_state,
)

PublicAPIState = _PublicAPIState


async def create_run(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
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

    state = get_public_state(request)
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
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = get_public_state(request)
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
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = get_public_state(request)
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
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
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
router = Router(routes=routes)
router.mount("/features", feature_router)
