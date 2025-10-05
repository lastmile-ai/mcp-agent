import json
import jwt
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
@pytest.fixture
def public_api_state():
    """Provide fresh state for each test and clean up after."""
    state = public_module.PublicAPIState()
    yield state
    # Teardown: clear state and cancel tasks
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
    c = TestClient(app())
    r = c.post("/v1/runs", json={"project_id": "p", "run_type": "x"})
    assert r.status_code == 401
def test_api_key_and_sse(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "k1,k2")
    c = TestClient(app(public_api_state))
    r = c.post("/v1/runs", headers={"X-API-Key": "k1"}, json={"project_id": "p", "run_type": "x"})
    assert r.status_code == 202
    run_id = r.json()["id"]
    events = []
    with c.stream("GET", f"/v1/stream/{run_id}", headers={"X-API-Key": "k1"}) as s:
        for line in s.iter_lines():
            if line and line.startswith(b"data: "):
                events.append(json.loads(line[6:].decode()))
                if events[-1]["event"] in ("completed", "cancelled"):
                    break
    names = [e["event"] for e in events]
    assert names == ["started", "progress", "completed"]
def test_jwt_hs256(monkeypatch, public_api_state):
    secret = "s3cr3t"
    monkeypatch.setenv("JWT_HS256_SECRET", secret)
    token = jwt.encode({"sub": "tool"}, secret, algorithm="HS256")
    c = TestClient(app(public_api_state))
    r = c.post("/v1/runs", headers={"Authorization": f"Bearer {token}"}, json={"project_id": "p", "run_type": "x"})
    assert r.status_code == 202
