from mcp_agent.telemetry.metrics import (
    budget_exceeded_total,
    llm_latency_ms,
    llm_tokens_input_total,
    llm_tokens_output_total,
    run_duration_ms,
    runs_in_progress,
    runs_total,
    sse_events_sent_total,
    test_duration_ms,
    tool_errors_total,
    tool_latency_ms,
)


def test_metrics_accept_measurements():
    run_duration_ms.record(1200, {"state": "green"})
    llm_latency_ms.record(250, {"model": "gpt"})
    tool_latency_ms.record(100, {"tool": "echo"})
    test_duration_ms.record(500, {"suite": "unit"})
    runs_total.add(1, {"state": "green"})
    llm_tokens_input_total.add(42, {"model": "gpt"})
    llm_tokens_output_total.add(21, {"model": "gpt"})
    tool_errors_total.add(1, {"code": "timeout"})
    budget_exceeded_total.add(1, {})
    sse_events_sent_total.add(3, {})
    runs_in_progress.add(1, {})

