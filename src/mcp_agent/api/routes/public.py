import asyncio
import json
import os
import time
import uuid
from typing import Dict, List, Tuple, Set

import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.llm.events import emit_llm_event
from mcp_agent.llm.gateway import LLMCallParams


class PublicAPIState:
    """Encapsulates all mutable state for the public API."""

    def __init__(self):
        self.runs: Dict[str, Dict] = {}
        # Changed: queues now maps run_id to a set of consumer queues
        self.queues: Dict[str, Set["asyncio.Queue[str]"]] = {}
        self.tasks: Set[asyncio.Task] = set()
        self.artifacts: Dict[str, tuple[bytes, str]] = {}

    async def cancel_all_tasks(self):
        """Cancel all tracked background tasks."""
        tasks = list(self.tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()

    def clear(self):
        """Clear all state dictionaries."""
        self.runs.clear()
        self.queues.clear()


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
    now = int(time.time())
    state.runs[run_id] = {"project_id": project_id, "run_type": run_type, "created": now, "status": "running"}
    # Changed: Initialize the set of consumer queues for this run
    state.queues[run_id] = set()

    async def _simulate():
        try:
            gateway = getattr(state, "llm_gateway", None)
            prompt_text = body.get("prompt")
            llm_enabled = os.getenv("MCP_LLM_GATEWAY_ENABLED", "").lower() in {"1", "true", "yes"}
            if (
                gateway
                and llm_enabled
                and isinstance(prompt_text, str)
                and prompt_text.strip()
            ):
                params_payload = body.get("llm_params")
                extra = params_payload if isinstance(params_payload, dict) else {}
                llm_params = LLMCallParams(
                    provider=body.get("provider"),
                    model=body.get("model"),
                    temperature=body.get("temperature"),
                    top_p=body.get("top_p"),
                    max_tokens=body.get("max_tokens"),
                    extra=extra,
                )
                cancel_token = asyncio.Event()
                try:
                    await gateway.run(
                        run_id=run_id,
                        trace_id=body.get("trace_id") or str(uuid.uuid4()),
                        prompt=prompt_text,
                        params=llm_params,
                        context_hash=body.get("context_hash"),
                        cancel_token=cancel_token,
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    state.runs[run_id]["status"] = "failed"
                    await emit_llm_event(
                        state,
                        run_id,
                        "llm/error",
                        {
                            "category": "gateway",
                            "message": str(exc),
                            "retryable": False,
                            "attempt": 1,
                            "violation": False,
                        },
                    )
                    raise
            await asyncio.sleep(0.01)
            # Broadcast progress event to all consumers
            for q in list(state.queues.get(run_id, [])):
                try:
                    await q.put(json.dumps({"event": "progress", "pct": 50, "ts": int(time.time())}))
                except Exception:
                    pass
            await asyncio.sleep(0.01)
            state.runs[run_id]["status"] = "completed"
            # Broadcast completed event and EOF to all consumers
            for q in list(state.queues.get(run_id, [])):
                try:
                    await q.put(json.dumps({"event": "completed", "ts": int(time.time())}))
                    await q.put("__EOF__")
                except Exception:
                    pass
        except Exception:
            # On error, send EOF to all consumers
            for q in list(state.queues.get(run_id, [])):
                try:
                    await q.put("__EOF__")
                except Exception:
                    pass

    task = asyncio.create_task(_simulate())
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    return JSONResponse({"id": run_id, "status": "running"}, status_code=202)


async def stream_run(request: Request) -> StreamingResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    run_id = request.path_params.get("id")
    state = _get_state(request)
    if run_id not in state.queues:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Changed: Create a new queue for this consumer and add it to the set
    consumer_queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues[run_id].add(consumer_queue)

    # Send initial started event to this consumer
    run_data = state.runs.get(run_id)
    if run_data:
        await consumer_queue.put(json.dumps({"event": "started", "run_id": run_id, "ts": run_data.get("created", int(time.time()))}))

    async def event_source():
        try:
            while True:
                try:
                    data = await consumer_queue.get()
                    if data == "__EOF__":
                        break
                    yield f"data: {data}\n\n"
                except asyncio.CancelledError:
                    break
                except Exception:
                    break
        finally:
            # Remove this consumer's queue from the set
            if run_id in state.queues:
                state.queues[run_id].discard(consumer_queue)

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
    # Broadcast cancellation to all consumers
    for q in list(state.queues.get(run_id, [])):
        try:
            await q.put(json.dumps({"event": "cancelled", "ts": int(time.time())}))
            await q.put("__EOF__")
        except Exception:
            pass
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
router = Router(routes=routes)
