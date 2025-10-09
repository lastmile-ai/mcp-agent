from importlib import import_module

Manifest = import_module("mcp_agent.context.models").Manifest
Slice = import_module("mcp_agent.context.models").Slice
compute_manifest_hash = import_module("mcp_agent.context.hash").compute_manifest_hash


def test_hash_determinism():
    s = Slice(uri="file:///a.py", start=0, end=10, bytes=100, token_estimate=25, reason="test")
    m1 = Manifest(slices=[s])
    m2 = Manifest(slices=[s])
    h1 = compute_manifest_hash(m1, code_version="v1", tool_versions={"t":"1"}, settings_fingerprint="abc")
    h2 = compute_manifest_hash(m2, code_version="v1", tool_versions={"t":"1"}, settings_fingerprint="abc")
    assert h1 == h2


def test_hash_changes_with_meta():
    s = Slice(uri="file:///a.py", start=0, end=10, bytes=100, token_estimate=25, reason="test")
    m = Manifest(slices=[s])
    h1 = compute_manifest_hash(m, code_version="v1", tool_versions={"t":"1"}, settings_fingerprint="abc")
    h2 = compute_manifest_hash(m, code_version="v2", tool_versions={"t":"1"}, settings_fingerprint="abc")
    assert h1 != h2
