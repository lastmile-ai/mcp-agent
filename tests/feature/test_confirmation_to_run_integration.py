import asyncio
import json
import threading

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
from mcp_agent.runloop.controller import RunController
from mcp_agent.runloop.lifecyclestate import RunState

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
        lifecycle,
        cancel_event=None,
        llm_budget=None,
        feature_spec=None,
        approved_budget_s=None,
    ):
        recorded["config"] = config
        recorded["feature_spec"] = feature_spec
        recorded["approved_budget_s"] = approved_budget_s
        recorded["lifecycle"] = lifecycle
        original_init(
            self,
            config=config,
            lifecycle=lifecycle,
            cancel_event=cancel_event,
            llm_budget=llm_budget,
            feature_spec=feature_spec,
            approved_budget_s=approved_budget_s,
        )

    monkeypatch.setattr(RunController, "__init__", capture_init)

    run_called = threading.Event()
    run_finished = threading.Event()

    async def fake_run(self):
        run_called.set()
        await self._lifecycle.transition_to(
            RunState.PREPARING,
            details={"trace_id": self._config.trace_id},
        )
        await self._lifecycle.transition_to(
            RunState.ASSEMBLING,
            details={"has_feature_spec": bool(self._feature_spec)},
        )
        await self._lifecycle.transition_to(
            RunState.PROMPTING,
            details={"iteration": 1, "budget": self._snapshot().as_dict()},
        )
        await self._lifecycle.transition_to(
            RunState.APPLYING,
            details={"iteration": 1, "budget": self._snapshot().as_dict()},
        )
        await self._lifecycle.transition_to(
            RunState.TESTING,
            details={"iteration": 1, "budget": self._snapshot().as_dict()},
        )
        await self._lifecycle.transition_to(
            RunState.GREEN,
            details={"iterations": self._config.iteration_count},
        )
        run_finished.set()

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

            assert run_called.wait(timeout=1.0)

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

            assert run_finished.wait(timeout=1.0)
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
