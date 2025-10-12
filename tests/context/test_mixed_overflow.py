import asyncio
from importlib import import_module

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")

def test_mixed_overflow_ordering():
    spans = [
        models.Span(uri="file:///a.py", start=0, end=20, section=1, priority=1),  # should fit
        models.Span(uri="file:///b.py", start=0, end=20, section=1, priority=1),  # may hit max_files or token
        models.Span(uri="file:///c.py", start=0, end=20, section=2, priority=1),  # section 2 may cap
    ]
    inputs = models.AssembleInputs(must_include=spans)
    opts = models.AssembleOptions(token_budget=10, max_files=1, section_caps={2:0}, neighbor_radius=0)
    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts))
    assert m.slices and m.slices[0].uri.endswith("a.py")
    # Expect both b and c overflow, with deterministic order by span key
    assert [ov["uri"] for ov in r.overflow] == ["file:///b.py", "file:///c.py"]
    reasons = {ov["uri"]: ov["reason"] for ov in r.overflow}
    assert reasons["file:///b.py"] in ("token_budget","max_files")
    assert reasons["file:///c.py"].startswith("section_cap_")
    assert r.violation is True
