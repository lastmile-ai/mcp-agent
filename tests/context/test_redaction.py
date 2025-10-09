import asyncio
from importlib import import_module
runtime = import_module("mcp_agent.context.runtime")
models = import_module("mcp_agent.context.models")
def test_sse_redaction(monkeypatch):
    # Redact any uri under file:///secret/*
    monkeypatch.setenv("MCP_CONTEXT_REDACT_PATH_GLOBS", '["file:///secret/*"]')
    store = runtime.MemoryArtifactStore()
    sse = runtime.MemorySSEEmitter()
    inputs = models.AssembleInputs(changed_paths=["file:///secret/file.py"])
    opts = models.AssembleOptions(neighbor_radius=0)
    m, h, r = asyncio.run(runtime.run_assembling_phase(
        run_id="r1",
        inputs=inputs,
        opts=opts,
        artifact_store=store,
        sse=sse,
        code_version="v1",
        repo="file:///secret/repo",
        commit_sha="deadbeef",
    ))
    end_evt = sse.events["r1"][-1]
    assert end_evt["phase"] == "ASSEMBLING"
    # example_uri should be redacted
    assert end_evt.get("example_uri") == ""
