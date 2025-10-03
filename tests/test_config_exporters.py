"""Tests for OpenTelemetry exporter configuration handling."""

import pytest

from mcp_agent.config import (
    ConsoleExporterSettings,
    FileExporterSettings,
    OTLPExporterSettings,
    OpenTelemetrySettings,
    TraceOTLPSettings,
    TracePathSettings,
)


def _assert_console_exporter(exporter):
    assert isinstance(exporter, ConsoleExporterSettings)
    assert exporter.type == "console"


def _assert_file_exporter(exporter):
    assert isinstance(exporter, FileExporterSettings)
    assert exporter.type == "file"


def _assert_otlp_exporter(exporter, endpoint: str):
    assert isinstance(exporter, OTLPExporterSettings)
    assert exporter.type == "otlp"
    assert exporter.endpoint == endpoint


def test_typed_exporters_passthrough():
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"type": "console"},
            {"type": "otlp", "endpoint": "http://collector:4318/v1/traces"},
        ],
    )

    assert len(settings.exporters) == 2
    _assert_console_exporter(settings.exporters[0])
    _assert_otlp_exporter(settings.exporters[1], "http://collector:4318/v1/traces")


def test_legacy_exporters_with_dict_settings():
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["file", "otlp"],
        path="/tmp/trace.jsonl",
        path_settings={
            "path_pattern": "traces/trace-{unique_id}.jsonl",
            "unique_id": "timestamp",
        },
        otlp_settings={
            "endpoint": "http://collector:4318/v1/traces",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    assert len(settings.exporters) == 2
    _assert_file_exporter(settings.exporters[0])
    assert settings.exporters[0].path == "/tmp/trace.jsonl"
    assert settings.exporters[0].path_settings
    assert (
        settings.exporters[0].path_settings.path_pattern
        == "traces/trace-{unique_id}.jsonl"
    )

    _assert_otlp_exporter(settings.exporters[1], "http://collector:4318/v1/traces")
    assert settings.exporters[1].headers == {"Authorization": "Bearer token"}


def test_legacy_exporters_with_base_models():
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["file", "otlp"],
        path_settings=TracePathSettings(path_pattern="trace-{unique_id}.jsonl"),
        otlp_settings=TraceOTLPSettings(endpoint="http://collector:4318/v1/traces"),
    )

    assert len(settings.exporters) == 2
    _assert_file_exporter(settings.exporters[0])
    assert settings.exporters[0].path_settings
    assert settings.exporters[0].path_settings.path_pattern == "trace-{unique_id}.jsonl"

    _assert_otlp_exporter(settings.exporters[1], "http://collector:4318/v1/traces")


def test_legacy_unknown_exporter_raises():
    with pytest.raises(ValueError, match="Unsupported OpenTelemetry exporter"):
        OpenTelemetrySettings(exporters=["console", "bogus"])


def test_literal_exporters_become_typed_configs():
    settings = OpenTelemetrySettings(exporters=["console", "file", "otlp"])

    assert len(settings.exporters) == 3
    assert [
        type(exporter) for exporter in settings.exporters
    ] == [
        ConsoleExporterSettings,
        FileExporterSettings,
        OTLPExporterSettings,
    ]
