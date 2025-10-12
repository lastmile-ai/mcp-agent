from importlib import import_module
import asyncio
assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")
def test_overflow_victim_ordering():
    # Create 3 spans that individually exceed a tiny token budget after the first two
    spans = [
        models.Span(uri="file:///a.py", start=0, end=8, section=1, priority=1, reason="r", tool="t"),
        models.Span(uri="file:///b.py", start=0, end=8, section=1, priority=1, reason="r", tool="t"),
        models.Span(uri="file:///c.py", start=0, end=8, section=1, priority=1, reason="r", tool="t"),
    ]
    inputs = models.AssembleInputs(must_include=spans)
    opts = models.AssembleOptions(token_budget=5, neighbor_radius=0)  # only one slice fits
    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts))
    # First one should be kept, next two should overflow in deterministic order
    assert m.slices[0].uri.endswith("a.py")
    assert [ov["uri"] for ov in r.overflow] == ["file:///b.py", "file:///c.py"]
    assert r.violation is True
