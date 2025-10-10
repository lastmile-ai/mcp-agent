import asyncio

from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module

API_KEY = "contract-key"


def build_app(state):
    app = Starlette()

    @app.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(app)
    return app


def test_contract_and_errors(monkeypatch):
    state = public_module.PublicAPIState()
    app = build_app(state)
    monkeypatch.setenv("FEATURE_CHAT_MAX_TURNS", "1")

    try:
        with TestClient(app) as client:
            # Unauthorized
            response = client.post("/v1/features/", json={"project_id": "x"})
            assert response.status_code == 401

            monkeypatch.setenv("STUDIO_API_KEYS", API_KEY)
            headers = {"X-API-Key": API_KEY}

            create = client.post("/v1/features/", json={"project_id": "proj"}, headers=headers)
            assert create.status_code == 201
            feature_id = create.json()["id"]

            invalid_role = client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "tool", "content": "nope"},
                headers=headers,
            )
            assert invalid_role.status_code == 400

            client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "user", "content": "draft"},
                headers=headers,
            )

            capped = client.post(
                f"/v1/features/{feature_id}/messages",
                json={"role": "assistant", "content": "should fail"},
                headers=headers,
            )
            assert capped.status_code == 400
            assert capped.json()["error"] == "chat_limit_reached"

            missing_spec = client.post(f"/v1/features/{feature_id}/estimate", json={}, headers=headers)
            assert missing_spec.status_code == 400

            cancel = client.post(f"/v1/features/{feature_id}/cancel", headers=headers)
            assert cancel.status_code == 200
            assert cancel.json()["state"] == "feature_cancelled"
    finally:
        asyncio.get_event_loop().run_until_complete(state.cancel_all_tasks())
        state.clear()
