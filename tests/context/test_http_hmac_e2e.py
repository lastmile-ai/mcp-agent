import asyncio
import json
import os
from importlib import import_module

import httpx

toolkit_mod = import_module("mcp_agent.context.toolkit")
assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")

def _mock_transport(handler):
    return httpx.MockTransport(handler)

def test_hmac_e2e_with_httpclient(monkeypatch):
    # Secret for HMAC
    monkeypatch.setenv("MCP_CONTEXT_HMAC_KEY", "sekret")
    # Mock transport that verifies X-Signature
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        # Expected HMAC
        import hashlib, hmac
        msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        exp = hmac.new(b"sekret", msg, hashlib.sha256).hexdigest()
        assert request.headers.get("X-Signature") == exp
        # Return small spans
        return httpx.Response(200, json={"spans":[{"uri":"file:///z.py","start":0,"end":10,"section":3,"priority":1}]})
    transport = _mock_transport(handler)

    # Build a toolkit with injected transport and fake registry entry
    tk = toolkit_mod.RegistryToolKit(trace_id="t", transport=transport, tool_versions={"tool":"1.0"})
    # Inject a fake capability mapping
    tk._tools = {"tool":{"base_url":"http://tool","caps":{"semantic_search"}}}

    inputs = models.AssembleInputs(task_targets=["anything"])
    opts = models.AssembleOptions(neighbor_radius=0)
    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts, toolkit=tk, tool_versions={"tool":"1.0"}, telemetry_attrs={"run_id":"r1"}))
    assert any(s.uri.endswith("z.py") for s in m.slices)
