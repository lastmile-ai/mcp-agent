import asyncio
import json
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.api.events_sse import RunEventStream
from mcp_agent.runloop.controller import RunCanceled, RunConfig, RunController
from mcp_agent.runloop.lifecyclestate import RunLifecycle, RunState

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
    stream = RunEventStream()
    lifecycle = RunLifecycle(run_id=run_id, stream=stream)
    await lifecycle.transition_to(
        RunState.QUEUED,
        details={"project_id": project_id, "run_type": run_type},
    )
    cancel_event = asyncio.Event()
    state.run_streams[run_id] = stream
    state.run_lifecycles[run_id] = lifecycle
    state.run_cancel_events[run_id] = cancel_event

    state.runs[run_id] = {
        "project_id": project_id,
        "run_type": run_type,
        "trace_id": trace_id,
        "status": "running",
        "state": lifecycle.state.value if lifecycle.state else None,
    }

    iterations = body.get("iterations")
    try:
        iteration_count = int(iterations)
    except (TypeError, ValueError):
        iteration_count = 1
    iteration_count = max(1, iteration_count)

    config = RunConfig(
        trace_id=trace_id,
        iteration_count=iteration_count,
        pack_hash=body.get("pack_hash"),
    )

    async def _run_controller() -> None:
        controller = RunController(
            config=config,
            lifecycle=lifecycle,
            cancel_event=cancel_event,
            llm_budget=budget,
        )
        try:
            await controller.run()
            state.runs[run_id]["status"] = "completed"
            state.runs[run_id]["state"] = RunState.GREEN.value
        except RunCanceled:
            state.runs[run_id]["status"] = "cancelled"
            state.runs[run_id]["state"] = RunState.CANCELED.value
        except Exception as exc:  # pragma: no cover - defensive
            state.runs[run_id]["status"] = "failed"
            if not lifecycle.is_terminal():
                await lifecycle.transition_to(
                    RunState.FAILED,
                    details={"reason": str(exc)},
                )
            state.runs[run_id]["state"] = RunState.FAILED.value

    task = asyncio.create_task(_run_controller())
    state.tasks.add(task)
    state.run_tasks[run_id] = task

    def _cleanup(_task: asyncio.Task) -> None:
        state.tasks.discard(task)
        state.run_tasks.pop(run_id, None)
        state.run_cancel_events.pop(run_id, None)

    task.add_done_callback(_cleanup)
    return JSONResponse(
        {"id": run_id, "status": "running", "state": RunState.QUEUED.value},
        status_code=202,
    )


async def stream_run(request: Request) -> StreamingResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = get_public_state(request)
    stream = state.run_streams.get(run_id)
    if stream is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def event_source():
        last_event_id_header = (
            request.headers.get("Last-Event-ID")
            or request.headers.get("last-event-id")
            or request.query_params.get("last_event_id")
        )
        try:
            last_event_id = int(last_event_id_header) if last_event_id_header else None
        except ValueError:
            last_event_id = None
        queue = stream.subscribe(last_event_id)
        try:
            while True:
                try:
                    event_id, data = await queue.get()
                    if event_id == -1 and data == "__EOF__":
                        break
                    yield f"id: {event_id}\ndata: {data}\n\n"
                except asyncio.CancelledError:
                    break
                except Exception:
                    break
        finally:
            stream.unsubscribe(queue)

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
    lifecycle = state.run_lifecycles.get(run_id)
    cancel_event = state.run_cancel_events.get(run_id)
    if lifecycle and lifecycle.is_terminal():
        return JSONResponse(
            {
                "id": run_id,
                "status": run.get("status", "cancelled"),
                "state": run.get("state", RunState.CANCELED.value),
            },
            status_code=200,
        )

    if cancel_event:
        cancel_event.set()
    run["status"] = "cancelled"

    task = state.run_tasks.get(run_id)
    if task and not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    if lifecycle and not lifecycle.is_terminal():
        await lifecycle.transition_to(
            RunState.CANCELED,
            details={"trigger": "api", "reason": "cancel_endpoint"},
        )
    state.runs[run_id]["state"] = RunState.CANCELED.value

    return JSONResponse(
        {"id": run_id, "status": "cancelled", "state": RunState.CANCELED.value},
        status_code=200,
    )


async def get_artifact(request: Request):
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
    art_id = request.path_params.get("id", "")
    if ":" in art_id:
        blob = state.artifacts.get(art_id)
        if not blob:
            return JSONResponse({"error": "not_found"}, status_code=404)
        data, content_type = blob
        try:
            payload = json.loads(data.decode("utf-8"))
            return JSONResponse(payload, media_type=content_type)
        except Exception:
            return JSONResponse({"error": "unsupported_content"}, status_code=415)

    path = request.query_params.get("path")
    if not path:
        index = state.artifact_index.build_index(art_id)
        return JSONResponse(index, status_code=200)
    try:
        data, media_type = state.artifact_index.get_artifact(art_id, path)
    except FileNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if media_type == "application/json":
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return JSONResponse({"error": "unsupported_content"}, status_code=415)
        return JSONResponse(payload, media_type=media_type)
    return JSONResponse({"error": "unsupported_content"}, status_code=415)


routes = [
    Route("/runs", create_run, methods=["POST"]),
    Route("/stream/{id}", stream_run, methods=["GET"]),
    Route("/runs/{id}/cancel", cancel_run, methods=["POST"]),
    Route("/artifacts/{id}", get_artifact, methods=["GET"]),
]
router = Router(routes=routes)
router.mount("/features", feature_router)
