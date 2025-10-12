import asyncio
import json
import time

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
from mcp_agent.runloop.controller import RunController
from mcp_agent.runloop.events import build_payload

API_KEY = "test-key"


def build_app(state):
    app = Starlette()

    @app.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(app)
    return app


def test_confirmation_starts_run(monkeypatch):
    monkeypatch.setenv("STUDIO_API_KEYS", API_KEY)
    state = public_module.PublicAPIState()

    recorded = {}
    original_init = RunController.__init__

    def capture_init(
        self,
        *,
        config,
        event_bus,
        llm_budget=None,
        feature_spec=None,
        approved_budget_s=None,
    ):
        recorded["config"] = config
        recorded["feature_spec"] = feature_spec
        recorded["approved_budget_s"] = approved_budget_s
        original_init(
            self,
            config=config,
            event_bus=event_bus,
            llm_budget=llm_budget,
            feature_spec=feature_spec,
            approved_budget_s=approved_budget_s,
        )

    monkeypatch.setattr(RunController, "__init__", capture_init)

    run_called = {"value": False}

    async def fake_run(self):
        run_called["value"] = True
        await self._event_bus.publish(
            build_payload(
                event="finished_green",
                trace_id=self._config.trace_id,
                iteration=self._config.iteration_count,
                pack_hash=self._config.pack_hash,
                budget=self._snapshot(),
            )
        )
        await self._event_bus.close()

    monkeypatch.setattr(RunController, "run", fake_run, raising=False)

    app = build_app(state)

    try:
        with TestClient(app) as client:
            headers = {"X-API-Key": API_KEY}
            create = client.post("/v1/features/", json={"project_id": "proj-123"}, headers=headers)
            assert create.status_code == 201
            feature_id = create.json()["id"]

            client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "user", "content": "Add a summary endpoint"},
                headers=headers,
            )

            spec_payload = {
                "spec": {
                    "summary": "Add project summary endpoint",
                    "details": "Expose /summary with totals.",
                    "targets": ["src/app/api.py", "tests/api/test_summary.py"],
                    "risks": ["security"],
                }
            }
            estimate = client.post(
                f"/v1/features/{feature_id}/estimate",
                json=spec_payload,
                headers=headers,
            )
            assert estimate.status_code == 200
            estimate_body = estimate.json()
            assert estimate_body["state"] == "awaiting_budget_confirmation"
            expected_seconds = estimate_body["estimate"]["seconds"]

            confirm = client.post(f"/v1/features/{feature_id}/confirm", headers=headers)
            assert confirm.status_code == 200
            confirm_body = confirm.json()
            run_id = confirm_body["run"]["id"]
            assert confirm_body["decision"]["seconds"] == expected_seconds

            for _ in range(100):
                if run_called["value"]:
                    break
                time.sleep(0.01)
            assert run_called["value"] is True

            with client.stream("GET", f"/v1/features/{feature_id}/events", headers=headers) as stream:
                seen = []
                for line in stream.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = json.loads(line[6:])
                    seen.append(payload["event"])
                    if payload["event"] == "starting_implementation":
                        break
            assert seen[:3] == [
                "feature_drafting",
                "feature_estimated",
                "awaiting_budget_confirmation",
            ]
            assert seen[-1] == "starting_implementation"

            detail = client.get(f"/v1/features/{feature_id}", headers=headers)
            assert detail.status_code == 200
            data = detail.json()
            assert data["decision"]["seconds"] == expected_seconds

            for _ in range(100):
                if state.runs[run_id]["status"] == "completed":
                    break
                time.sleep(0.01)
            assert state.runs[run_id]["feature_id"] == feature_id
            assert state.runs[run_id]["status"] == "completed"

            config = recorded["config"]
            assert config.approved_budget_s == expected_seconds
            assert config.feature_spec["summary"] == "Add project summary endpoint"
            feature_spec = recorded["feature_spec"]
            assert feature_spec.summary == "Add project summary endpoint"
            assert recorded["approved_budget_s"] == expected_seconds
    finally:
        asyncio.run(state.cancel_all_tasks())
        state.clear()
