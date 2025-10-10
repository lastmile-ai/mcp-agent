import asyncio
import importlib
import random
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
def otel_env(monkeypatch):
    # Ensure test telemetry is not bypassed by global OTEL disablement toggles.
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_PYTHON_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)

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

    yield {
        "tracer_provider": tracer_provider,
        "meter_provider": meter_provider,
        "span_exporter": span_exporter,
        "metric_reader": metric_reader,
    }

    # Cleanup after test
    trace._TRACER_PROVIDER = None
    metrics._METER_PROVIDER = None


@pytest.fixture
def mock_httpx_post(mocker):
    return mocker.patch("httpx.AsyncClient.post")


@pytest.mark.asyncio
async def test_metrics_and_traces_emitted(otel_env, mock_httpx_post):
    """Test that successful tool call emits metrics and traces."""
    from mcp_agent.tool_clients import adapters

    # Reload to use the test providers
    importlib.reload(adapters)

    random_id = random.randint(100000, 999999)
    tool_name = f"test_tool_{random_id}"
    tool_description = f"Test tool {random_id}"

    # Mock successful response
    mock_httpx_post.return_value = httpx.Response(
        200,
        json={"content": [{"type": "text", "text": f"Success {random_id}"}]},
    )

    client = adapters.HTTPToolClient(base_url=f"http://test{random_id}.local")

    result = await client.call_tool(
        tool_name,
        {"arg": "value"},
        description=tool_description,
    )

    assert result["content"][0]["text"] == f"Success {random_id}"

    # Verify metrics
    metrics_data = otel_env["metric_reader"].get_metrics_data()
    resource_metrics = metrics_data.resource_metrics
    assert len(resource_metrics) > 0

    # Verify traces
    spans = otel_env["span_exporter"].get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == f"call_tool {tool_name}"
    assert spans[0].attributes["tool.name"] == tool_name
