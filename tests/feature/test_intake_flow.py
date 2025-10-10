import asyncio
import json

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module


API_KEY = "test-key"


def build_app(state):
    app = Starlette()

    @app.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(app)
    return app


def test_full_intake_flow(monkeypatch):
    monkeypatch.setenv("STUDIO_API_KEYS", API_KEY)
    state = public_module.PublicAPIState()
    app = build_app(state)

    try:
        with TestClient(app) as client:
            headers = {"X-API-Key": API_KEY}
            create = client.post("/v1/features/", json={"project_id": "proj-1"}, headers=headers)
            assert create.status_code == 201
            feature_id = create.json()["id"]

            msg1 = client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "user", "content": "Need a summary endpoint"},
                headers=headers,
            )
            assert msg1.status_code == 200

            msg2 = client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "assistant", "content": "Let's define the spec"},
                headers=headers,
            )
            assert msg2.status_code == 200

            spec_payload = {
                "spec": {
                    "summary": "Add project summary endpoint",
                    "details": "Expose /summary with totals.",
                    "targets": ["src/app/api.py", "tests/api/test_summary.py"],
                    "risks": ["security review"],
                }
            }
            estimate = client.post(
                f"/v1/features/{feature_id}/estimate", json=spec_payload, headers=headers
            )
            assert estimate.status_code == 200
            body = estimate.json()
            assert body["estimate"]["seconds"] >= 480
            assert body["state"] == "awaiting_budget_confirmation"

            confirm = client.post(f"/v1/features/{feature_id}/confirm", headers=headers)
            assert confirm.status_code == 200
            payload = confirm.json()
            run_id = payload["run"]["id"]

            with client.stream(f"GET", f"/v1/features/{feature_id}/events", headers=headers) as stream:
                events = []
                for line in stream.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    events.append(event["event"])
                    if event["event"] == "starting_implementation":
                        break
            assert events[:3] == ["feature_drafting", "feature_estimated", "awaiting_budget_confirmation"]
            assert "budget_confirmed" in events
            assert events[-1] == "starting_implementation"

            detail = client.get(f"/v1/features/{feature_id}", headers=headers)
            assert detail.status_code == 200
            data = detail.json()
            assert data["decision"]["seconds"] == payload["decision"]["seconds"]
            assert len(data["artifacts"]) == 4
            assert all(a.startswith(f"mem://{feature_id}/artifacts/feature/{feature_id}/") for a in data["artifacts"])

            assert state.runs[run_id]["status"] in {"running", "completed"}
    finally:
        asyncio.get_event_loop().run_until_complete(state.cancel_all_tasks())
        state.clear()
