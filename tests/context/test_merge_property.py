from importlib import import_module
import asyncio
import random

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")

def rnd_spans(n=100):
    spans = []
    for _ in range(n):
        s = random.randint(0, 1000)
        e = s + random.randint(1, 50)
        spans.append(models.Span(uri="file:///x.py", start=s, end=e, section=3, priority=random.randint(0,2)))
    return spans

def test_merge_idempotent():
    inputs = models.AssembleInputs(must_include=rnd_spans(200))
    opts = models.AssembleOptions(neighbor_radius=0)
    m1, h1, r1 = asyncio.run(assemble.assemble_context(inputs, opts))
    m2, h2, r2 = asyncio.run(assemble.assemble_context(inputs, opts))
    assert [ (s.uri,s.start,s.end) for s in m1.slices ] == [ (s.uri,s.start,s.end) for s in m2.slices ]
