import asyncio
from importlib import import_module

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")


def test_merge_and_budget_and_filters():
    # Overlapping spans that should merge and then be budget-limited
    spans = [
        models.Span(uri="file:///m.py", start=0, end=100, section=3, priority=1, reason="seed"),
        models.Span(uri="file:///m.py", start=50, end=120, section=3, priority=2, reason="seed"),
        models.Span(uri="file:///x.py", start=0, end=40, section=3, priority=1, reason="seed"),
    ]
    inputs = models.AssembleInputs(must_include=spans, never_include=[models.Span(uri="file:///x.py", start=0, end=40)])
    # Token budget small to force overflow after first merged file
    opts = models.AssembleOptions(token_budget=30, neighbor_radius=0)

    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts))
    # After merge, m.py one slice, x.py removed by never_include
    assert any(s.uri.endswith("m.py") for s in m.slices)
    assert not any(s.uri.endswith("x.py") for s in m.slices)
    # Budget applied, only one file included
    assert r.files_out == 1
    # Overflow recorded for token budget
    assert r.pruned.get("token_budget", 0) >= 0
