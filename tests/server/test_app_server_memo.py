import pytest
from types import SimpleNamespace


class FakeWorkflow:
    def __init__(self):
        self.captured_memo = None

    @classmethod
    async def create(cls, name: str, context):
        return cls()

    async def run_async(self, *args, **kwargs):
        # Capture the internal memo passed by the server layer
        self.captured_memo = kwargs.get("__mcp_agent_workflow_memo")
        # Return a minimal execution-like object
        return SimpleNamespace(workflow_id="wf-1", run_id="run-1")


@pytest.mark.anyio
async def test_memo_from_forwarded_headers(monkeypatch):
    from mcp_agent.server import app_server

    # Patch workflow resolution to return our FakeWorkflow and a dummy context
    monkeypatch.setattr(
        app_server,
        "_resolve_workflows_and_context",
        lambda ctx: ({"TestWorkflow": FakeWorkflow}, SimpleNamespace()),
    )
    # Avoid registry side effects
    monkeypatch.setattr(app_server, "_register_session", lambda *a, **k: None)

    # Construct a request-like object with only X-Forwarded-* headers
    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "app.mcpac.dev",
        "X-Forwarded-Prefix": "/abc123",
    }
    req = SimpleNamespace(headers=headers, base_url="https://ignored/base/")
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(request=req), fastmcp=SimpleNamespace()
    )

    # Run the private helper
    result = await app_server._workflow_run(ctx, "TestWorkflow")
    assert result["workflow_id"] == "wf-1"
    assert result["run_id"] == "run-1"

    # Verify FakeWorkflow captured memo with full URL reconstructed from X-Forwarded-*
    # Fetch the workflow instance created within _workflow_run by inspecting patched resolution
    # Easiest: call again but capture via a local workflow instance
    # Alternatively, patch FakeWorkflow to store last_memo globally; simpler approach below:

    # Build a workflow instance and invoke run_async directly to assert memo composition via same code path
    # Instead, patch FakeWorkflow.create to stash instance
    captured = {}

    async def create_and_stash(name: str, context):
        wf = FakeWorkflow()
        captured["wf"] = wf
        return wf

    monkeypatch.setattr(
        FakeWorkflow,
        "create",
        classmethod(lambda cls, name, context: create_and_stash(name, context)),
    )

    _ = await app_server._workflow_run(ctx, "TestWorkflow")
    memo = captured["wf"].captured_memo
    assert memo is not None
    assert memo.get("gateway_url") == "https://app.mcpac.dev/abc123"
    # No token provided in headers
    assert memo.get("gateway_token") in (None, "")


@pytest.mark.anyio
async def test_memo_falls_back_to_env(monkeypatch):
    from mcp_agent.server import app_server

    monkeypatch.setattr(
        app_server,
        "_resolve_workflows_and_context",
        lambda ctx: ({"TestWorkflow": FakeWorkflow}, SimpleNamespace()),
    )
    monkeypatch.setattr(app_server, "_register_session", lambda *a, **k: None)

    # No headers at all; env should be used
    req = SimpleNamespace(headers={}, base_url=None)
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(request=req), fastmcp=SimpleNamespace()
    )

    monkeypatch.setenv("MCP_GATEWAY_URL", "http://example:9000/base")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "secret-token")

    captured = {}

    async def create_and_stash(name: str, context):
        wf = FakeWorkflow()
        captured["wf"] = wf
        return wf

    monkeypatch.setattr(
        FakeWorkflow,
        "create",
        classmethod(lambda cls, name, context: create_and_stash(name, context)),
    )

    _ = await app_server._workflow_run(ctx, "TestWorkflow")
    memo = captured["wf"].captured_memo
    assert memo is not None
    assert memo.get("gateway_url") == "http://example:9000/base"
    assert memo.get("gateway_token") == "secret-token"
