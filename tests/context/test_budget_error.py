import asyncio
from importlib import import_module

import pytest

assemble = import_module("mcp_agent.context.assemble")
models = import_module("mcp_agent.context.models")
telemetry = import_module("mcp_agent.context.telemetry")
errors = import_module("mcp_agent.context.errors")


def _build_inputs() -> models.AssembleInputs:
    spans = [
        models.Span(uri="file:///a.py", start=0, end=200, section=1, priority=1, reason="seed"),
        models.Span(uri="file:///b.py", start=0, end=200, section=1, priority=1, reason="seed"),
    ]
    return models.AssembleInputs(must_include=spans)


def test_budget_error_raised():
    opts = models.AssembleOptions(token_budget=10, neighbor_radius=0, enforce_non_droppable=True)
    with pytest.raises(errors.BudgetError) as excinfo:
        asyncio.run(assemble.assemble_context(_build_inputs(), opts))
    assert "budget" in str(excinfo.value).lower()
    assert excinfo.value.overflow


def test_overflow_metric_increment(monkeypatch):
    calls = []

    def _capture(count, reason, attrs=None):
        calls.append((count, reason, attrs))

    monkeypatch.setattr(telemetry, "record_overflow", _capture)

    opts = models.AssembleOptions(token_budget=10, neighbor_radius=0)
    asyncio.run(assemble.assemble_context(_build_inputs(), opts))

    assert any(count > 0 for count, _reason, _attrs in calls)
    assert any(reason == "token_budget" for _count, reason, _attrs in calls)
