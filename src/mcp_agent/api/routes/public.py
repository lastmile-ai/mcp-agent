import asyncio
import json
import os
import time
import uuid
from typing import Dict, List, Tuple

import jwt
from starlette.responses import JSONResponse, StreamingResponse
from starlette.requests import Request
from starlette.routing import Route, Router

_RUNS: Dict[str, Dict] = {}
_QUEUES: Dict[str, "asyncio.Queue[str]"] = {}

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

    run_id = str(uuid.uuid4())
    now = int(time.time())
    _RUNS[run_id] = {"project_id": project_id, "run_type": run_type, "created": now, "status": "running"}
    q: asyncio.Queue[str] = asyncio.Queue()
    _QUEUES[run_id] = q

    await q.put(json.dumps({"event": "started", "run_id": run_id, "ts": now}))

    async def _simulate():
        try:
            await asyncio.sleep(0.01)
            await q.put(json.dumps({"event": "progress", "pct": 50, "ts": int(time.time())}))
            await asyncio.sleep(0.01)
            _RUNS[run_id]["status"] = "completed"
            await q.put(json.dumps({"event": "completed", "ts": int(time.time())}))
            await q.put("__EOF__")
        except Exception:
            await q.put("__EOF__")

    asyncio.create_task(_simulate())

    return JSONResponse({"id": run_id, "status": "running"}, status_code=202)

async def stream_run(request: Request) -> StreamingResponse:
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    run_id = request.path_params.get("id")
    if run_id not in _QUEUES:
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def event_source():
        q = _QUEUES[run_id]
        while True:
            data = await q.get()
            if data == "__EOF__":
                break
            yield f"data: {data}\n\n"

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)

async def cancel_run(request: Request):
    ok, _ = _authenticate(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    run_id = request.path_params.get("id")
    run = _RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "not_found"}, status_code=404)
    run["status"] = "cancelled"
    q = _QUEUES.get(run_id)
    if q:
        await q.put(json.dumps({"event": "cancelled", "ts": int(time.time())}))
        await q.put("__EOF__")
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
