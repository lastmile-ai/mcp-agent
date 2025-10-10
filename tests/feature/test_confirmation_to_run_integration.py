import asyncio
import json

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module

API_KEY = "run-key"


def build_app(state):
    app = Starlette()

    @app.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(app)
    return app


def create_feature(client, headers):
    resp = client.post("/v1/features/", json={"project_id": "proj"}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def estimate_feature(client, headers, feature_id):
    spec_payload = {
        "spec": {
            "summary": "Add health check",
            "details": "Expose GET /health and test",
            "targets": ["src/app/health.py"],
            "risks": [],
        }
    }
    resp = client.post(f"/v1/features/{feature_id}/estimate", json=spec_payload, headers=headers)
    assert resp.status_code == 200
    return resp.json()


def test_confirmation_starts_runloop(monkeypatch):
    monkeypatch.setenv("STUDIO_API_KEYS", API_KEY)
    state = public_module.PublicAPIState()
    app = build_app(state)

    try:
        with TestClient(app) as client:
            headers = {"X-API-Key": API_KEY}
            feature_id = create_feature(client, headers)
            estimate = estimate_feature(client, headers, feature_id)
            assert estimate["estimate"]["iterations"] >= 4

            confirm = client.post(f"/v1/features/{feature_id}/confirm", headers=headers)
            assert confirm.status_code == 200
            run_id = confirm.json()["run"]["id"]

            with client.stream(f"GET", f"/v1/stream/{run_id}", headers=headers) as stream:
                events = []
                for line in stream.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = json.loads(line[6:])
                    events.append(payload["event"])
                    if payload["event"] == "finished_green":
                        break
            assert events[0] == "initializing_run"
            assert events[-1] == "finished_green"

            feature_events = state.feature_manager.bus(feature_id)._history
            assert any("starting_implementation" in e for e in feature_events)
    finally:
        asyncio.get_event_loop().run_until_complete(state.cancel_all_tasks())
        state.clear()
