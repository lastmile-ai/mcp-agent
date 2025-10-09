from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Dict, Optional, List

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.api.routes import public as pub
from mcp_agent.context.models import AssembleInputs
from mcp_agent.api.context_engine_integration import assemble_before_prompt
from mcp_agent.context.settings import ContextSettings
from mcp_agent.context.logutil import redact_event


class _StateSSEEmitter:
    """Adapter that writes runtime SSE events into the existing public API queues."""
    def __init__(self, state):
        self.state = state

    async def emit(self, run_id: str, event: Dict[str, Any]) -> None:
        # Put onto all queues subscribed to this run
        queues = self.state.queues.get(run_id, [])
        evt = json.dumps({"event": "context", **event})
        for q in list(queues):
            try:
                await q.put(evt)
            except Exception:
                pass


class _StateArtifactStore:
    """Simple artifact store held in PublicAPIState for GET /v1/artifacts."""
    def __init__(self, state):
        self.state = state
        if not hasattr(self.state, "artifacts"):
            self.state.artifacts = {}  # type: ignore[attr-defined]

    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/json") -> str:
        aid = f"{run_id}:{path}"
        self.state.artifacts[aid] = (data, content_type)
        return f"mem://{aid}"


async def _create_run_with_context(request: Request) -> JSONResponse:
    # Delegate to original create_run to keep semantics
    base_resp: JSONResponse = await pub.create_run(request)
    if base_resp.status_code != 200:
        return base_resp

    payload = json.loads(base_resp.body.decode("utf-8"))
    run_id = payload.get("id") or payload.get("run_id")
    if not run_id:
        return base_resp

    state = pub._get_state(request)  # type: ignore[attr-defined]

    # Derive inputs from request body; fall back to empty
    try:
        req_body = await request.json()
    except Exception:
        req_body = {}

    inputs = AssembleInputs.model_validate(req_body.get("context_inputs", {
        "task_targets": req_body.get("task_targets", []),
        "changed_paths": req_body.get("changed_paths", []),
        "referenced_files": req_body.get("referenced_files", []),
        "failing_tests": req_body.get("failing_tests", []),
        "must_include": req_body.get("must_include", []),
        "never_include": req_body.get("never_include", []),
    }))

    cfg = ContextSettings()

    # Kick off assembling in background tied to state lifecycle
    async def _bg():
        try:
            await assemble_before_prompt(
                run_id=run_id,
                inputs=inputs,
                repo=req_body.get("repo"),
                commit_sha=req_body.get("commit_sha"),
                code_version=req_body.get("code_version"),
                tool_versions=req_body.get("tool_versions"),
                artifact_store=_StateArtifactStore(state),
                sse=_StateSSEEmitter(state),
            )
        except Exception:
            # Update run status on enforce
            if ContextSettings().ENFORCE_NON_DROPPABLE:
                try:
                    state.runs.setdefault(run_id, {})["status"] = "failed"
                except Exception:
                    pass
            # Signal violation or error via SSE
            queues = state.queues.get(run_id, [])
            evt = json.dumps({"event":"context","phase":"ASSEMBLING","status":"error","violation": True})
            for q in list(queues):
                try: await q.put(evt)
                except Exception: pass

    # Announce start immediately
    queues = state.queues.get(run_id, [])
    start_evt = {"phase":"ASSEMBLING","status":"start","run_id":run_id}
    red = redact_event(start_evt, cfg.REDACT_PATH_GLOBS)
    for q in list(queues):
        try: await q.put(json.dumps({"event":"context", **red}))
        except Exception: pass

    asyncio.create_task(_bg())
    return base_resp


async def _get_artifact_overlay(request: Request):
    ok, _ = pub._authenticate(request)  # reuse same auth
    if not ok:
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    # Try overlay store first, then fall back to original handler
    state = pub._get_state(request)
    art_id = request.path_params.get("id", "")
    blob = getattr(state, "artifacts", {}).get(art_id)
    if blob:
        data, content_type = blob
        return JSONResponse(json.loads(data.decode("utf-8")), media_type=content_type)
    return await pub.get_artifact(request)


routes = [
    Route("/runs", _create_run_with_context, methods=["POST"]),
    Route("/stream/{id}", pub.stream_run, methods=["GET"]),  # reuse
    Route("/runs/{id}/cancel", pub.cancel_run, methods=["POST"]),  # reuse
    Route("/artifacts/{id}", _get_artifact_overlay, methods=["GET"]),
]
router = Router(routes=routes)


def add_public_api_with_context(app):
    # Mount our router at /v1, shadowing originals without removing them
    app.router.mount("/v1", router)
