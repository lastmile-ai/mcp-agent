import asyncio
import threading

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
from mcp_agent.runloop.controller import RunController

API_KEY = "artifact-key"


def build_app(state):
    app = Starlette()

    @app.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(app)
    return app


def test_feature_artifact_paths(monkeypatch):
    monkeypatch.setenv("STUDIO_API_KEYS", API_KEY)
    state = public_module.PublicAPIState()
    app = build_app(state)

    try:
        run_started = threading.Event()

        async def fake_run(self):
            run_started.set()

        monkeypatch.setattr(RunController, "run", fake_run, raising=False)

        with TestClient(app) as client:
            headers = {"X-API-Key": API_KEY}
            feature = client.post("/v1/features/", json={"project_id": "proj"}, headers=headers)
            feature_id = feature.json()["id"]

            spec_payload = {
                "spec": {
                    "summary": "Document layout",
                    "details": "Write docs for layout",
                    "targets": ["docs/layout.md"],
                    "risks": [],
                }
            }
            client.post(f"/v1/features/{feature_id}/estimate", json=spec_payload, headers=headers)
            client.post(f"/v1/features/{feature_id}/confirm", json={"seconds": 600}, headers=headers)

            assert run_started.wait(timeout=1.0)

            expected = {
                f"mem://{feature_id}/artifacts/feature/{feature_id}/spec.md",
                f"mem://{feature_id}/artifacts/feature/{feature_id}/transcript.ndjson",
                f"mem://{feature_id}/artifacts/feature/{feature_id}/estimate.json",
                f"mem://{feature_id}/artifacts/feature/{feature_id}/decision.json",
            }
            assert set(state.artifacts.keys()) == expected
    finally:
        asyncio.run(state.cancel_all_tasks())
        state.clear()
