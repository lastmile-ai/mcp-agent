"""Tracer configuration tests."""

import pytest

from mcp_agent.config import OpenTelemetrySettings, OTLPExporterSettings
from mcp_agent.tracing.tracer import TracingConfig


def _install_tracer_stubs(monkeypatch):
    recorded_exporters = []
    provider_kwargs = []

    class StubOTLPExporter:
        def __init__(self, *, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers
            recorded_exporters.append(self)

    class StubBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

        def on_start(self, *_, **__):  # pragma: no cover - interface stub
            pass

        def on_end(self, *_, **__):  # pragma: no cover - interface stub
            pass

        def shutdown(self, *_, **__):  # pragma: no cover - interface stub
            pass

        def force_flush(self, *_, **__):  # pragma: no cover - interface stub
            pass

    class StubTracerProvider:
        def __init__(self, **kwargs):
            provider_kwargs.append(kwargs)
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

        def shutdown(self):  # pragma: no cover - interface stub
            pass

    monkeypatch.setattr("mcp_agent.tracing.tracer.OTLPSpanExporter", StubOTLPExporter)
    monkeypatch.setattr(
        "mcp_agent.tracing.tracer.BatchSpanProcessor", StubBatchSpanProcessor
    )
    monkeypatch.setattr("mcp_agent.tracing.tracer.TracerProvider", StubTracerProvider)
    monkeypatch.setattr(TracingConfig, "_global_provider_set", True, raising=False)
    monkeypatch.setattr(
        TracingConfig, "_instrumentation_initialized", True, raising=False
    )

    return recorded_exporters, provider_kwargs


@pytest.mark.anyio
async def test_multiple_otlp_exporters(monkeypatch):
    recorded_exporters, _ = _install_tracer_stubs(monkeypatch)

    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            OTLPExporterSettings(endpoint="http://collector-a:4318/v1/traces"),
            OTLPExporterSettings(
                endpoint="http://collector-b:4318/v1/traces",
                headers={"X-Auth": "token"},
            ),
        ],
    )

    tracer_config = TracingConfig()
    await tracer_config.configure(settings, session_id="test-session", force=True)

    assert [exp.endpoint for exp in recorded_exporters] == [
        "http://collector-a:4318/v1/traces",
        "http://collector-b:4318/v1/traces",
    ]
    assert recorded_exporters[1].headers == {"X-Auth": "token"}


@pytest.mark.anyio
async def test_sample_rate_only_applied_when_specified(monkeypatch):
    _, provider_kwargs = _install_tracer_stubs(monkeypatch)

    settings_default = OpenTelemetrySettings(
        enabled=True,
        exporters=[{"type": "console"}],
    )
    tracer_config = TracingConfig()
    await tracer_config.configure(settings_default, session_id="session-1", force=True)

    assert "sampler" not in provider_kwargs[0]
    assert provider_kwargs[0]["resource"] is not None

    settings_with_rate = OpenTelemetrySettings(
        enabled=True,
        exporters=[{"type": "console"}],
        sample_rate=0.5,
    )
    tracer_config = TracingConfig()
    await tracer_config.configure(
        settings_with_rate, session_id="session-2", force=True
    )

    assert "sampler" in provider_kwargs[1]
