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

llm_provider_fallback_total = _meter.create_counter(
    "llm_provider_fallback_total",
    unit="1",
    description="Number of times the LLM gateway failed over to a different provider.",
)

llm_budget_abort_total = _meter.create_counter(
    "llm_budget_abort_total",
    unit="1",
    description="Count of streaming runs aborted due to hitting a configured budget.",
)

llm_sse_consumer_count = _meter.create_up_down_counter(
    "llm_sse_consumer_count",
    unit="1",
    description="Current number of active LLM SSE stream consumers.",
)

__all__ = [
    "llm_tokens_total",
    "llm_failures_total",
    "llm_provider_fallback_total",
    "llm_budget_abort_total",
    "llm_sse_consumer_count",
]
