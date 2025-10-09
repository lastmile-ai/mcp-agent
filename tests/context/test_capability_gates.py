import asyncio
from importlib import import_module

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")

class FakeToolKit(assemble.ToolKit):
    async def semantic_search(self, query: str, top_k: int):
        # Return two spans for the query
        return [
            models.Span(uri="file:///q.py", start=10, end=30, section=3, priority=1, reason="q", tool="semantic_search"),
            models.Span(uri="file:///w.py", start=0, end=5, section=3, priority=1, reason="q", tool="semantic_search"),
        ]

    async def symbols(self, target: str):
        return [models.Span(uri=str(target), start=0, end=2, section=2, priority=1, reason="sym", tool="symbols")]

    async def neighbors(self, uri: str, line_or_start: int, radius: int):
        return [models.Span(uri=str(uri), start=max(0, line_or_start - 1), end=line_or_start + 1, section=2, priority=1, reason="nbr", tool="neighbors")]

    async def patterns(self, globs):
        return []


def test_capability_gates_and_determinism():
    inputs = models.AssembleInputs(task_targets=["refactor api"], referenced_files=["file:///a.py"], failing_tests=[{"path":"file:///t.py","line":5}])
    opts = models.AssembleOptions(top_k=5, neighbor_radius=2)

    m1, h1, r1 = asyncio.run(assemble.assemble_context(inputs, opts, toolkit=FakeToolKit()))
    m2, h2, r2 = asyncio.run(assemble.assemble_context(inputs, opts, toolkit=FakeToolKit()))

    assert h1 == h2
    assert len(m1.slices) == len(m2.slices)
    assert r1.spans_in == r2.spans_in
