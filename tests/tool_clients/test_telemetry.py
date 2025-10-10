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

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(resource=Resource.create({}), metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    span_exporter = _ListSpanExporter()
    tracer_provider = TracerProvider(resource=Resource.create({}))
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    module = importlib.import_module("mcp_agent.client.http")
    module = importlib.reload(module)
    return module, metric_reader, span_exporter


def test_metrics_and_traces_emitted(otel_env, caplog):
    asyncio.run(_metrics_and_traces_emitted(otel_env, caplog))


async def _metrics_and_traces_emitted(otel_env, caplog) -> None:
    http_module, metric_reader, span_exporter = otel_env

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, json={"error": "nope"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    config = http_module.HTTPClientConfig(retry_max=2, breaker_enabled=False)

    caplog.set_level("INFO")

    async with httpx.AsyncClient(transport=transport) as async_client:
        tool_client = http_module.HTTPToolClient(
            "telemetry-tool",
            "https://example.com",
            client=async_client,
            config=config,
            rng=random.Random(2),
        )
        response = await tool_client.request("GET", "/telemetry")
        assert response.status_code == 200

    metrics_data = metric_reader.get_metrics_data()
    histogram_points = []
    retry_points = []
    for resource_metrics in metrics_data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "http_client_latency_ms":
                    histogram_points.extend(metric.data.data_points)
                if metric.name == "http_client_retries_total":
                    retry_points.extend(metric.data.data_points)

    assert len(histogram_points) == 1
    assert histogram_points[0].attributes["tool"] == "telemetry-tool"
    assert histogram_points[0].attributes["method"] == "GET"

    assert len(retry_points) == 1
    assert retry_points[0].value == 1
    assert retry_points[0].attributes["reason"] == "5xx"

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes.get("retry_count") == 1
    assert span.attributes.get("breaker_state") in {"closed", "disabled"}

    log_messages = "\n".join(record.message for record in caplog.records)
    assert '"phase": "retry"' in log_messages
    assert '"phase": "recv"' in log_messages
