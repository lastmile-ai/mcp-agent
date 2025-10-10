"""Shared telemetry primitives for the MCP agent."""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("mcp-agent.llm.gateway")

llm_tokens_total = _meter.create_counter(
    "llm_tokens_total",
    unit="1",
    description="Total tokens observed by the LLM gateway, split by provider/model/kind.",
)

llm_failures_total = _meter.create_counter(
    "llm_failures_total",
    unit="1",
    description="Count of LLM gateway failures grouped by provider/model/category.",
)

__all__ = ["llm_tokens_total", "llm_failures_total"]
