import asyncio
import json
from importlib import import_module

runtime = import_module("mcp_agent.context.runtime")
models = import_module("mcp_agent.context.models")
assemble_mod = import_module("mcp_agent.context.assemble")


class TinyToolKit(assemble_mod.ToolKit):
    async def semantic_search(self, query: str, top_k: int):
        return []
    async def symbols(self, target: str):
        return []
    async def neighbors(self, uri: str, line_or_start: int, radius: int):
        return []
    async def patterns(self, globs):
        return []


def test_runloop_assembling_phase_persists_and_emits():
    run_id = "r-123"
    inputs = models.AssembleInputs(changed_paths=["file:///x.py"])
    opts = models.AssembleOptions(neighbor_radius=0)

    store = runtime.MemoryArtifactStore()
    sse = runtime.MemorySSEEmitter()

    m, h, r = asyncio.run(runtime.run_assembling_phase(
        run_id=run_id,
        inputs=inputs,
        opts=opts,
        toolkit=TinyToolKit(),
        artifact_store=store,
        sse=sse,
        code_version="v1",
        tool_versions={"tool":"1.0"},
    ))

    # SSE events start and end
    assert run_id in sse.events
    evts = sse.events[run_id]
    assert evts[0]["phase"] == "ASSEMBLING" and evts[0]["status"] == "start"
    assert evts[-1]["status"] == "end"
    assert evts[-1]["pack_hash"] == m.meta.pack_hash

    # Artifact persisted
    data = store.get(run_id, "artifacts/context/manifest.json")
    payload = json.loads(data.decode("utf-8"))
    assert payload["meta"]["pack_hash"] == m.meta.pack_hash
    assert len(payload["slices"]) >= 1  # includes changed_paths seed
