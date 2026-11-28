"""human_input_request must be delivered to the execution-mapped session."""

from __future__ import annotations

import pytest
import httpx
from httpx import ASGITransport

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import (
    _PENDING_PROMPTS,
    _RUN_CONTEXT_REGISTRY,
    _RUN_EXECUTION_ID_REGISTRY,
    _RUN_IDENTITY_REGISTRY,
    _RUN_LOGGING_SESSION,
    _RUN_SESSION_REGISTRY,
    _get_session,
    _register_session,
    _resolve_upstream_session_for_execution,
    create_mcp_server_for_app,
)


class DummyUpstreamSession:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[dict] = []

    async def send_log_message(self, level, data, logger, related_request_id=None):
        self.calls.append(
            {
                "level": level,
                "data": data,
                "logger": logger,
                "related_request_id": related_request_id,
            }
        )


@pytest.fixture
def clean_session_registries():
    _RUN_SESSION_REGISTRY.clear()
    _RUN_EXECUTION_ID_REGISTRY.clear()
    _RUN_IDENTITY_REGISTRY.clear()
    _RUN_CONTEXT_REGISTRY.clear()
    _RUN_LOGGING_SESSION.clear()
    _PENDING_PROMPTS.clear()
    yield
    _RUN_SESSION_REGISTRY.clear()
    _RUN_EXECUTION_ID_REGISTRY.clear()
    _RUN_IDENTITY_REGISTRY.clear()
    _RUN_CONTEXT_REGISTRY.clear()
    _RUN_LOGGING_SESSION.clear()
    _PENDING_PROMPTS.clear()


@pytest.mark.asyncio
async def test_resolve_prefers_mapped_session_over_fallback(clean_session_registries):
    mapped = DummyUpstreamSession("mapped")
    fallback = DummyUpstreamSession("fallback")
    await _register_session(run_id="exec-a", execution_id="exec-a", session=mapped)

    session, used_fallback = await _resolve_upstream_session_for_execution(
        "exec-a", fallback
    )

    assert session is mapped
    assert used_fallback is False


@pytest.mark.asyncio
async def test_resolve_uses_fallback_when_no_mapping(clean_session_registries):
    fallback = DummyUpstreamSession("fallback")

    session, used_fallback = await _resolve_upstream_session_for_execution(
        "exec-missing", fallback
    )

    assert session is fallback
    assert used_fallback is True


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_session_available(clean_session_registries):
    session, used_fallback = await _resolve_upstream_session_for_execution(
        "exec-missing", None
    )

    assert session is None
    assert used_fallback is False


async def _post_human_prompt(mcp, execution_id: str, prompt_text: str = "approve?"):
    transport = ASGITransport(app=mcp.sse_app())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.post(
            "/internal/human/prompts",
            json={
                "execution_id": execution_id,
                "prompt": {"text": prompt_text},
                "metadata": {
                    "workflow_id": "wf-1",
                    "signal_name": "human_input",
                },
            },
        )


@pytest.mark.asyncio
async def test_human_prompt_delivered_to_mapped_session_not_latest(
    clean_session_registries,
):
    app = MCPApp(name="human-input-route")
    await app.initialize()
    try:
        client_a = DummyUpstreamSession("client-a")
        client_b = DummyUpstreamSession("client-b")
        app._last_known_upstream_session = client_b
        app._upstream_session = client_b

        mcp = create_mcp_server_for_app(app)
        await _register_session(
            run_id="exec-a", execution_id="exec-a", session=client_a
        )

        response = await _post_human_prompt(mcp, "exec-a")

        assert response.status_code == 200
        body = response.json()
        assert "request_id" in body
        assert len(client_a.calls) == 1
        assert client_b.calls == []
        payload = client_a.calls[0]["data"]
        assert payload["kind"] == "human_input_request"
        assert payload["request_id"] == body["request_id"]
        assert payload["prompt"]["text"] == "approve?"
        assert client_a.calls[0]["logger"] == "mcp_agent.human"
        # Mapping must stay on Client A, not be rebound to the latest client.
        assert await _get_session("exec-a") is client_a
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_human_prompt_uses_fallback_when_unmapped(clean_session_registries):
    app = MCPApp(name="human-input-fallback")
    await app.initialize()
    try:
        client_b = DummyUpstreamSession("client-b")
        app._last_known_upstream_session = client_b

        mcp = create_mcp_server_for_app(app)
        response = await _post_human_prompt(mcp, "exec-new", prompt_text="need input")

        assert response.status_code == 200
        assert len(client_b.calls) == 1
        assert client_b.calls[0]["data"]["prompt"]["text"] == "need input"
        assert await _get_session("exec-new") is client_b
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_human_prompt_returns_503_when_no_session(clean_session_registries):
    app = MCPApp(name="human-input-missing")
    await app.initialize()
    try:
        mcp = create_mcp_server_for_app(app)
        response = await _post_human_prompt(mcp, "exec-none")

        assert response.status_code == 503
        assert response.json()["error"] == "session_not_available"
    finally:
        await app.cleanup()
