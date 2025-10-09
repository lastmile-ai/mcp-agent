import asyncio
from importlib import import_module

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")
compute_manifest_hash = import_module("mcp_agent.context.hash").compute_manifest_hash


def test_ordering_and_hash_stability_ties():
    spans = [
        models.Span(uri="file:///a.py", start=10, end=20, section=3, priority=1, reason="r", tool="t"),
        models.Span(uri="file:///a.py", start=0, end=5, section=3, priority=1, reason="r", tool="t"),
        models.Span(uri="file:///b.py", start=0, end=5, section=3, priority=1, reason="r", tool="t"),
    ]
    inputs = models.AssembleInputs(must_include=spans)
    opts = models.AssembleOptions(neighbor_radius=0)

    m1, h1, r1 = asyncio.run(assemble.assemble_context(inputs, opts))
    m2, h2, r2 = asyncio.run(assemble.assemble_context(inputs, opts))

    # Stable order
    uris1 = [s.uri for s in m1.slices]
    uris2 = [s.uri for s in m2.slices]
    assert uris1 == uris2
    assert h1 == h2
