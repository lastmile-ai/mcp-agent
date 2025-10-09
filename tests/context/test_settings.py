import os
from importlib import import_module

ContextSettings = import_module("mcp_agent.context.settings").ContextSettings


def test_settings_defaults_and_fingerprint(monkeypatch):
    s = ContextSettings()
    fp1 = s.fingerprint()
    assert s.TOP_K == 25
    assert s.NEIGHBOR_RADIUS == 20

    monkeypatch.setenv("MCP_CONTEXT_TOP_K", "30")
    s2 = ContextSettings()
    fp2 = s2.fingerprint()

    assert s2.TOP_K == 30
    assert fp1 != fp2
