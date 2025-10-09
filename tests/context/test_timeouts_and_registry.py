import asyncio
import time
from importlib import import_module

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")

class SlowToolKit(assemble.ToolKit):
    async def semantic_search(self, query: str, top_k: int):
        await asyncio.sleep(0.2)
        return []
    async def symbols(self, target: str):
        await asyncio.sleep(0.2)
        return []
    async def neighbors(self, uri: str, line_or_start: int, radius: int):
        await asyncio.sleep(0.2)
        return []
    async def patterns(self, globs):
        await asyncio.sleep(0.2)
        return []

def test_timeouts_are_enforced():
    # Set tiny timeouts via options; assemble should not hang > ~0.2s per call
    inputs = models.AssembleInputs(task_targets=["a"], referenced_files=["file:///a.py"], failing_tests=[{"path":"file:///t.py","line":1}], must_include=[], never_include=[])
    opts = models.AssembleOptions(top_k=1, neighbor_radius=1, token_budget=None, max_files=None, section_caps={}, enforce_non_droppable=False, timeouts_ms={"semantic": 10, "symbols": 10, "neighbors": 10, "patterns": 10})
    t0 = time.perf_counter()
    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts, toolkit=SlowToolKit()))
    dt = time.perf_counter() - t0
    assert dt < 0.5  # calls should short-timeout
