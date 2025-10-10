"""Feature intake API endpoints."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.budget.llm_budget import LLMBudget
from mcp_agent.feature.events import emit_drafting, emit_starting_implementation
from mcp_agent.feature.models import FeatureDraft, MessageRole
from mcp_agent.runloop.controller import RunConfig, RunController
from mcp_agent.runloop.events import EventBus

from .public import _authenticate, _get_state


def _bool_env(name: str) -> bool:
    val = os.getenv(name, "false").lower()
    return val in {"1", "true", "yes", "on"}


async def create_feature(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    project_id = body.get("project_id")
    trace_id = body.get("trace_id")
    if not isinstance(project_id, str):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)

    state = _get_state(request)
    draft = state.feature_manager.create(project_id=project_id, trace_id=trace_id)
    await emit_drafting(state.feature_manager.bus(draft.feature_id), draft)
    return JSONResponse({"id": draft.feature_id, "state": draft.state.value}, status_code=201)


async def _ensure_feature(request: Request) -> tuple[FeatureDraft | None, JSONResponse | None]:
    feature_id = request.path_params.get("id") or ""
    state = _get_state(request)
    draft = state.feature_manager.get(feature_id)
    if draft is None:
        return None, JSONResponse({"error": "not_found"}, status_code=404)
    return draft, None


async def append_message(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    role = body.get("role", "user")
    content = body.get("content")
    if not isinstance(content, str):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)
    try:
        message_role = MessageRole(role)
    except ValueError:
        return JSONResponse({"error": "invalid_role"}, status_code=400)

    max_turns = int(os.getenv("FEATURE_CHAT_MAX_TURNS", "0"))
    if max_turns > 0 and len(draft.messages) >= max_turns:
        return JSONResponse({"error": "chat_limit_reached"}, status_code=400)

    state = _get_state(request)
    draft = await state.feature_manager.append_message(draft.feature_id, message_role, content)
    return JSONResponse(draft.as_dict(), status_code=200)


async def estimate_feature(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    spec_payload = body.get("spec")
    if not isinstance(spec_payload, dict):
        return JSONResponse({"error": "invalid_schema"}, status_code=400)

    state = _get_state(request)
    await state.feature_manager.freeze_spec(draft.feature_id, spec_payload)
    draft = await state.feature_manager.estimate(draft.feature_id)

    response: Dict[str, Any] = draft.as_dict()

    if _bool_env("FEATURE_BUDGET_AUTO_CONFIRM"):
        draft, run_payload = await _auto_confirm(state, draft)
        response.update({"decision": draft.decision.as_dict(), "run": run_payload})
    return JSONResponse(response, status_code=200)


async def confirm_feature(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}

    seconds = body.get("seconds")
    rationale = body.get("rationale")
    override = None
    if seconds is not None:
        try:
            override = int(seconds)
        except (TypeError, ValueError):
            return JSONResponse({"error": "invalid_schema"}, status_code=400)

    state = _get_state(request)
    draft = await state.feature_manager.confirm(draft.feature_id, seconds=override, rationale=rationale)
    run_payload = await _start_implementation(state, draft)
    return JSONResponse({"status": "confirmed", "decision": draft.decision.as_dict(), "run": run_payload}, status_code=200)


async def cancel_feature(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    state = _get_state(request)
    draft = await state.feature_manager.cancel(draft.feature_id)
    return JSONResponse({"status": "cancelled", "state": draft.state.value}, status_code=200)


async def get_feature(request: Request) -> JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    state = _get_state(request)
    data = draft.as_dict()
    artifact_prefix = f"mem://{draft.feature_id}/"
    artifacts = [aid for aid in state.artifacts.keys() if aid.startswith(artifact_prefix)]
    data["artifacts"] = artifacts
    return JSONResponse(data, status_code=200)


async def stream_feature_events(request: Request) -> StreamingResponse | JSONResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    draft, error = await _ensure_feature(request)
    if error:
        return error
    state = _get_state(request)
    event_bus = state.feature_manager.bus(draft.feature_id)

    async def event_source():
        queue = event_bus.subscribe()
        try:
            while True:
                data = await queue.get()
                if data == "__EOF__":
                    break
                yield f"data: {data}\n\n"
        finally:
            event_bus.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


async def _start_implementation(state, draft) -> Dict[str, Any]:
    estimate = draft.estimate
    decision = draft.decision
    if estimate is None or decision is None or draft.spec is None:
        raise RuntimeError("feature_not_ready")
    run_id = str(uuid.uuid4())
    trace_id = draft.trace_id
    budget = LLMBudget(limit_seconds=decision.seconds)
    event_bus = EventBus()
    state.event_buses[run_id] = event_bus
    state.runs[run_id] = {
        "project_id": draft.project_id,
        "run_type": "feature_implementation",
        "trace_id": trace_id,
        "status": "running",
        "feature_id": draft.feature_id,
    }
    config = RunConfig(
        trace_id=trace_id,
        iteration_count=estimate.iterations,
        pack_hash=None,
        feature_spec=draft.spec.as_dict(),
        approved_budget_s=decision.seconds,
        caps=estimate.caps,
    )

    async def _run_controller() -> None:
        controller = RunController(
            config=config,
            event_bus=event_bus,
            llm_budget=budget,
            feature_spec=draft.spec,
            approved_budget_s=decision.seconds,
        )
        try:
            await controller.run()
            state.runs[run_id]["status"] = "completed"
        except Exception:  # pragma: no cover - defensive
            state.runs[run_id]["status"] = "failed"
            await event_bus.close()

    task = asyncio.create_task(_run_controller())
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    await emit_starting_implementation(state.feature_manager.bus(draft.feature_id), draft, run_id)
    return {"id": run_id, "iterations": estimate.iterations, "seconds": decision.seconds}


async def _auto_confirm(state, draft):
    draft = await state.feature_manager.confirm(draft.feature_id)
    run_payload = await _start_implementation(state, draft)
    return draft, run_payload


routes = [
    Route("/", create_feature, methods=["POST"]),
    Route("/{id}", get_feature, methods=["GET"]),
    Route("/{id}/messages", append_message, methods=["POST"]),
    Route("/{id}/estimate", estimate_feature, methods=["POST"]),
    Route("/{id}/confirm", confirm_feature, methods=["POST"]),
    Route("/{id}/cancel", cancel_feature, methods=["POST"]),
    Route("/{id}/events", stream_feature_events, methods=["GET"]),
]

router = Router(routes=routes)
