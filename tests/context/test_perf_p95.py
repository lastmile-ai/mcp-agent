import asyncio
import time
from importlib import import_module
assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")
def test_perf_p95_tiny_corpus():
    inputs = models.AssembleInputs(changed_paths=["file:///a.py"])
    opts = models.AssembleOptions(neighbor_radius=0)
    durs = []
    for _ in range(30):
        t0 = time.perf_counter()
        m, h, r = asyncio.run(assemble.assemble_context(inputs, opts))
        durs.append((time.perf_counter()-t0)*1000.0)
    durs.sort()
    p95 = durs[int(len(durs)*0.95)-1]
    assert p95 < 200.0  # ms
