import asyncio
import json
import os
import time
import uuid
from typing import Dict, List, Tuple, Set
import jwt
from starlette.responses import JSONResponse, StreamingResponse
from starlette.requests import Request
from starlette.routing import Route, Router


class PublicAPIState:
    """Encapsulates all mutable state for the public API."""

    def __init__(self):
        self.runs: Dict[str, Dict] = {}
        # Changed: queues now maps run_id to a set of consumer queues
        self.queues: Dict[str, Set["asyncio.Queue[str]"]] = {}
        self.tasks: Set[asyncio.Task] = set()

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
    return JSONResponse({"error": "not_found"}, status_code=404)


routes = [
    Route("/runs", create_run, methods=["POST"]),
    Route("/stream/{id}", stream_run, methods=["GET"]),
    Route("/runs/{id}/cancel", cancel_run, methods=["POST"]),
    Route("/artifacts/{id}", get_artifact, methods=["GET"]),
]
router = Router(routes=routes)
