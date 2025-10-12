import importlib
import os
import random
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult, SpanExporter


class _ListSpanExporter(SpanExporter):
    def __init__(self) -> None:
        self._spans = []

    def export(self, spans):
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self._spans.clear()

    def get_finished_spans(self):
        return list(self._spans)


@pytest.fixture
def otel_env():
    # Ensure test telemetry is not bypassed by global OTEL disablement toggles.
    env_keys = [
        "OTEL_SDK_DISABLED",
        "OTEL_PYTHON_DISABLED",
        "OTEL_METRICS_EXPORTER",
        "OTEL_TRACES_EXPORTER",
    ]
    previous_env = {key: os.environ.get(key) for key in env_keys}
    for key in env_keys:
        os.environ.pop(key, None)

    # Reset global providers to allow setting new ones in tests
    # This is needed to prevent "Overriding of current TracerProvider is not allowed" warning
    trace._TRACER_PROVIDER = None
    metrics._METER_PROVIDER = None

    span_exporter = _ListSpanExporter()
    tracer_provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=Resource.create({"service.name": "test"}))
    metrics.set_meter_provider(meter_provider)

    try:
        yield {
            "tracer_provider": tracer_provider,
            "meter_provider": meter_provider,
            "span_exporter": span_exporter,
            "metric_reader": metric_reader,
        }
    finally:
        # Cleanup after test
        trace._TRACER_PROVIDER = None
        metrics._METER_PROVIDER = None
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def mock_httpx_request():
    async_request = AsyncMock()
    with patch.object(httpx.AsyncClient, "request", async_request):
        yield async_request


@pytest.mark.asyncio
async def test_metrics_and_traces_emitted(otel_env, mock_httpx_request):
    """Test that successful tool call emits metrics and traces."""
    from mcp_agent.client import http as http_client_module

    # Reload to use the test providers
    importlib.reload(http_client_module)

    random_id = random.randint(100000, 999999)
    tool_name = f"test_tool_{random_id}"
    tool_description = f"Test tool {random_id}"

    # Mock successful response
    mock_httpx_request.return_value = httpx.Response(
        200,
        json={"content": [{"type": "text", "text": f"Success {random_id}"}]},
    )

    client = http_client_module.HTTPToolClient(
        tool_name,
        base_url=f"http://test{random_id}.local",
    )

    response = await client.request(
        "POST",
        "/call",
        json={"tool": tool_name, "arguments": {"arg": "value"}, "description": tool_description},
    )

    assert response.json()["content"][0]["text"] == f"Success {random_id}"

    # Ensure pending telemetry is exported before inspecting the collectors.
    otel_env["tracer_provider"].force_flush()
    otel_env["meter_provider"].force_flush()

    # Verify metrics
    metrics_data = otel_env["metric_reader"].get_metrics_data()
    assert metrics_data is not None
    resource_metrics = metrics_data.resource_metrics
    assert len(resource_metrics) > 0

    # Verify traces
    spans = otel_env["span_exporter"].get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "tool.http"
    assert span.attributes["tool"] == tool_name
    assert span.attributes["http.method"] == "POST"
