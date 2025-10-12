import asyncio
import json
import jwt
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
from mcp_agent.runloop.controller import RunController
from mcp_agent.runloop.lifecyclestate import RunState

@pytest.fixture
def public_api_state():
    """Provide fresh state for each test and clean up after."""
    state = public_module.PublicAPIState()
    yield state
    # Teardown: clear state and cancel tasks
    asyncio.run(state.cancel_all_tasks())
    state.clear()

@pytest.fixture
async def public_api_state_async():
    """Async fixture providing fresh state for each test with proper teardown."""
    state = public_module.PublicAPIState()
    yield state
    # Teardown: cancel all tasks and clear state
    await state.cancel_all_tasks()
    state.clear()

def app(state=None):
    """Create Starlette app with optional injected state."""
    a = Starlette()
    if state:
        # Inject state via middleware
        @a.middleware("http")
        async def inject_state(request, call_next):
            request.state.public_api_state = state
            return await call_next(request)
    add_public_api(a)
    return a

def test_unauthorized():
    with TestClient(app()) as c:
        r = c.post("/v1/runs", json={"project_id": "p", "run_type": "x"})
        assert r.status_code == 401

def test_api_key_and_sse(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "k1,k2")
    with TestClient(app(public_api_state)) as c:
        r = c.post("/v1/runs", headers={"X-API-Key": "k1"}, json={"project_id": "p", "run_type": "x"})
        assert r.status_code == 202
        run_id = r.json()["id"]
        assert r.json()["state"] == RunState.QUEUED.value
        events = []
        event_ids = []
        with c.stream("GET", f"/v1/stream/{run_id}", headers={"X-API-Key": "k1"}) as s:
            current_id = None
            for line in s.iter_lines():
                if not line:
                    continue
                if line.startswith("id: "):
                    current_id = int(line[4:])
                    continue
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                events.append(payload)
                if current_id is not None:
                    event_ids.append(current_id)
                if payload["state"] in {
                    RunState.GREEN.value,
                    RunState.FAILED.value,
                    RunState.CANCELED.value,
                }:
                    break

        states = [e["state"] for e in events]
        assert states == [
            RunState.QUEUED.value,
            RunState.PREPARING.value,
            RunState.ASSEMBLING.value,
            RunState.PROMPTING.value,
            RunState.APPLYING.value,
            RunState.TESTING.value,
            RunState.GREEN.value,
        ]
        assert all(event["run_id"] == run_id for event in events)
        assert all("timestamp" in event for event in events)
        assert events[0]["details"]["project_id"] == "p"
        # Ensure SSE ids are monotonically increasing starting from 1.
        assert event_ids == sorted(event_ids)
        assert event_ids[0] == 1


def test_sse_reconnect_last_event_id(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "k1")
    with TestClient(app(public_api_state)) as c:
        r = c.post(
            "/v1/runs",
            headers={"X-API-Key": "k1"},
            json={"project_id": "p", "run_type": "x", "iterations": 1},
        )
        assert r.status_code == 202
        run_id = r.json()["id"]
        assert r.json()["state"] == RunState.QUEUED.value
        events = []
        last_id = None
        with c.stream("GET", f"/v1/stream/{run_id}", headers={"X-API-Key": "k1"}) as s:
            current_id = None
            for line in s.iter_lines():
                if not line:
                    continue
                if line.startswith("id: "):
                    current_id = int(line[4:])
                    continue
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                events.append(payload["state"])
                last_id = current_id
                if len(events) == 3:
                    break

        assert last_id is not None

        resumed = []
        with c.stream(
            "GET",
            f"/v1/stream/{run_id}",
            headers={"X-API-Key": "k1", "Last-Event-ID": str(last_id)},
        ) as s:
            current_id = None
            for line in s.iter_lines():
                if not line:
                    continue
                if line.startswith("id: "):
                    current_id = int(line[4:])
                    continue
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                resumed.append(payload["state"])
                if payload["state"] in {RunState.GREEN.value, RunState.CANCELED.value, RunState.FAILED.value}:
                    break

        combined = events + resumed
        assert combined == [
            RunState.QUEUED.value,
            RunState.PREPARING.value,
            RunState.ASSEMBLING.value,
            RunState.PROMPTING.value,
            RunState.APPLYING.value,
            RunState.TESTING.value,
            RunState.GREEN.value,
        ]


def test_cancel_run_emits_canceled_state(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "k1")

    async def controlled_run(self):
        await self._cancel_event.wait()
        await self._ensure_not_canceled()

    monkeypatch.setattr(RunController, "run", controlled_run, raising=False)

    with TestClient(app(public_api_state)) as c:
        r = c.post(
            "/v1/runs",
            headers={"X-API-Key": "k1"},
            json={"project_id": "p", "run_type": "x", "iterations": 3},
        )
        assert r.status_code == 202
        run_id = r.json()["id"]
        assert r.json()["state"] == RunState.QUEUED.value
        cancel_resp = c.post(f"/v1/runs/{run_id}/cancel", headers={"X-API-Key": "k1"})
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["state"] == RunState.CANCELED.value

        events: list[str] = []
        stream_headers = {"X-API-Key": "k1", "Last-Event-ID": "0"}
        with c.stream("GET", f"/v1/stream/{run_id}", headers=stream_headers) as s:
            current_id = None
            for line in s.iter_lines():
                if not line:
                    continue
                if line.startswith("id: "):
                    current_id = int(line[4:])
                    continue
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                events.append(payload["state"])

        assert events[0] == RunState.QUEUED.value
        assert events[-1] == RunState.CANCELED.value
        assert public_api_state.runs[run_id]["status"] == "cancelled"

def test_jwt_hs256(monkeypatch, public_api_state):
    secret = "s3cr3t"
    monkeypatch.setenv("JWT_HS256_SECRET", secret)
    token = jwt.encode({"sub": "tool"}, secret, algorithm="HS256")
    with TestClient(app(public_api_state)) as c:
        r = c.post("/v1/runs", headers={"Authorization": f"Bearer {token}"}, json={"project_id": "p", "run_type": "x"})
        assert r.status_code == 202
