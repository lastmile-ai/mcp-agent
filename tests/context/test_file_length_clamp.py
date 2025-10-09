import asyncio
from importlib import import_module
assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")
def test_neighborhood_clamp_with_file_lengths(tmp_path):
    # Create a temp file of 50 bytes
    p = tmp_path / "x.py"
    p.write_text("a"*50, encoding="utf-8")
    uri = f"file://{p}"
    # Span near the end should clamp to file size after neighborhood
    ms = [models.Span(uri=uri, start=45, end=49, section=3, priority=1)]
    inputs = models.AssembleInputs(must_include=ms)
    opts = models.AssembleOptions(neighbor_radius=20)
    setattr(opts, "file_lengths", {uri: 50})
    m, h, r = asyncio.run(assemble.assemble_context(inputs, opts))
    sl = next(s for s in m.slices if s.uri == uri)
    assert sl.end <= 50
