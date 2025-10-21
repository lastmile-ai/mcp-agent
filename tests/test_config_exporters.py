"""Tests for OpenTelemetry exporter configuration handling across different formats."""

import pytest
from pydantic_core import ValidationError

from mcp_agent.config import (
    OpenTelemetrySettings,
    Settings,
    TraceOTLPSettings,
    TracePathSettings,
)


def _assert_console_exporter(exporter):
    """Assert that exporter is in key-discriminated console format: {console: {...}}."""
    assert isinstance(exporter, dict)
    assert "console" in exporter
    assert isinstance(exporter["console"], dict)


def _assert_file_exporter(exporter, path=None, path_pattern=None):
    """Assert that exporter is in key-discriminated file format with optional path checks."""
    assert isinstance(exporter, dict)
    assert "file" in exporter
    file_config = exporter["file"]
    assert isinstance(file_config, dict)
    if path is not None:
        assert file_config.get("path") == path
    if path_pattern is not None:
        assert file_config.get("path_settings") is not None
        path_settings = file_config["path_settings"]
        if isinstance(path_settings, dict):
            assert path_settings.get("path_pattern") == path_pattern
        else:
            assert path_settings.path_pattern == path_pattern


def _assert_otlp_exporter(
    exporter, endpoint: str | None = None, headers: dict | None = None
):
    """Assert that exporter is in key-discriminated OTLP format with optional field checks."""
    assert isinstance(exporter, dict)
    assert "otlp" in exporter
    otlp_config = exporter["otlp"]
    assert isinstance(otlp_config, dict)
    if endpoint is not None:
        assert otlp_config.get("endpoint") == endpoint
    if headers is not None:
        assert otlp_config.get("headers") == headers


# ============================================================================
# String Exporter Tests (with legacy top-level fields)
# ============================================================================


def test_v1_string_exporters_with_legacy_fields():
    """Test string exporters with top-level path/otlp_settings."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["console", "file", "otlp"],
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

    assert len(settings.exporters) == 3
    _assert_console_exporter(settings.exporters[0])
    _assert_file_exporter(
        settings.exporters[1],
        path="/tmp/trace.jsonl",
        path_pattern="traces/trace-{unique_id}.jsonl",
    )
    _assert_otlp_exporter(
        settings.exporters[2],
        endpoint="http://collector:4318/v1/traces",
        headers={"Authorization": "Bearer token"},
    )


def test_v1_file_exporter_with_base_model_path_settings():
    """Test string exporter with TracePathSettings as BaseModel."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["file"],
        path_settings=TracePathSettings(
            path_pattern="trace-{unique_id}.jsonl",
            unique_id="session_id",
        ),
    )

    assert len(settings.exporters) == 1
    file_exp = settings.exporters[0]
    _assert_file_exporter(file_exp)
    file_config = file_exp["file"]
    assert file_config.get("path_settings") is not None
    path_settings = file_config["path_settings"]
    if isinstance(path_settings, dict):
        assert path_settings.get("path_pattern") == "trace-{unique_id}.jsonl"
        assert path_settings.get("unique_id") == "session_id"
    else:
        assert path_settings.path_pattern == "trace-{unique_id}.jsonl"
        assert path_settings.unique_id == "session_id"


def test_v1_otlp_exporter_with_base_model():
    """Test string exporter with TraceOTLPSettings as BaseModel."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["otlp"],
        otlp_settings=TraceOTLPSettings(
            endpoint="http://collector:4318/v1/traces",
            headers={"X-Custom-Header": "value"},
        ),
    )

    assert len(settings.exporters) == 1
    _assert_otlp_exporter(
        settings.exporters[0],
        endpoint="http://collector:4318/v1/traces",
        headers={"X-Custom-Header": "value"},
    )


def test_v1_string_exporters_without_legacy_fields():
    """Test string exporters without legacy fields (should create empty settings)."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["console", "file", "otlp"],
    )

    assert len(settings.exporters) == 3
    _assert_console_exporter(settings.exporters[0])
    _assert_file_exporter(settings.exporters[1])  # No path or path_settings
    _assert_otlp_exporter(settings.exporters[2])  # No endpoint or headers


# ============================================================================
# Type-Discriminated Exporter Tests (using 'type' field)
# ============================================================================


def test_v2_type_discriminated_union():
    """Test exporters with 'type' discriminator field."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"type": "console"},
            {"type": "file", "path": "/var/log/traces.jsonl"},
            {"type": "otlp", "endpoint": "http://collector:4318/v1/traces"},
        ],
    )

    assert len(settings.exporters) == 3
    _assert_console_exporter(settings.exporters[0])
    _assert_file_exporter(settings.exporters[1], path="/var/log/traces.jsonl")
    _assert_otlp_exporter(
        settings.exporters[2], endpoint="http://collector:4318/v1/traces"
    )


def test_v2_multiple_otlp_exporters():
    """Test type-discriminated format supports multiple OTLP exporters with different endpoints."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"type": "otlp", "endpoint": "http://collector1:4318"},
            {
                "type": "otlp",
                "endpoint": "http://collector2:4318",
                "headers": {"X-API-Key": "secret"},
            },
        ],
    )

    assert len(settings.exporters) == 2
    _assert_otlp_exporter(settings.exporters[0], endpoint="http://collector1:4318")
    _assert_otlp_exporter(
        settings.exporters[1],
        endpoint="http://collector2:4318",
        headers={"X-API-Key": "secret"},
    )


def test_v2_file_exporter_with_path_settings():
    """Test type-discriminated file exporter with nested path_settings."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {
                "type": "file",
                "path": "/tmp/trace.jsonl",
                "path_settings": {
                    "path_pattern": "logs/{unique_id}.jsonl",
                    "unique_id": "timestamp",
                    "timestamp_format": "%Y%m%d",
                },
            }
        ],
    )

    assert len(settings.exporters) == 1
    file_exp = settings.exporters[0]
    _assert_file_exporter(file_exp, path="/tmp/trace.jsonl")
    file_config = file_exp["file"]
    path_settings = file_config.get("path_settings")
    assert path_settings is not None
    if isinstance(path_settings, dict):
        assert path_settings.get("path_pattern") == "logs/{unique_id}.jsonl"
        assert path_settings.get("timestamp_format") == "%Y%m%d"
    else:
        assert path_settings.path_pattern == "logs/{unique_id}.jsonl"
        assert path_settings.timestamp_format == "%Y%m%d"


# ============================================================================
# Key-Discriminated Exporter Tests (dict key, no 'type' field)
# ============================================================================


def test_v3_dict_key_discriminator():
    """Test key-discriminated format: exporters use dict keys as discriminators."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"console": {}},
            {"file": {"path": "/var/log/traces.jsonl"}},
            {"otlp": {"endpoint": "http://collector:4318/v1/traces"}},
        ],
    )

    assert len(settings.exporters) == 3
    _assert_console_exporter(settings.exporters[0])
    _assert_file_exporter(settings.exporters[1], path="/var/log/traces.jsonl")
    _assert_otlp_exporter(
        settings.exporters[2], endpoint="http://collector:4318/v1/traces"
    )


def test_v3_multiple_exporters_same_type():
    """Test key-discriminated format supports multiple exporters of the same type."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"otlp": {"endpoint": "http://primary-collector:4318"}},
            {
                "otlp": {
                    "endpoint": "http://backup-collector:4318",
                    "headers": {"X-Region": "us-west"},
                }
            },
            {"otlp": {"endpoint": "https://cloud-collector.example.com:4318"}},
        ],
    )

    assert len(settings.exporters) == 3
    _assert_otlp_exporter(
        settings.exporters[0], endpoint="http://primary-collector:4318"
    )
    _assert_otlp_exporter(
        settings.exporters[1],
        endpoint="http://backup-collector:4318",
        headers={"X-Region": "us-west"},
    )
    _assert_otlp_exporter(
        settings.exporters[2], endpoint="https://cloud-collector.example.com:4318"
    )


def test_v3_file_exporter_with_advanced_path_settings():
    """Test key-discriminated file exporter with complex path_settings."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {
                "file": {
                    "path": "a/b/c/d",
                    "path_settings": {
                        "path_pattern": "logs/mcp-agent-{unique_id}.jsonl",
                        "unique_id": "timestamp",
                        "timestamp_format": "%Y%m%d_%H%M%S",
                    },
                }
            }
        ],
    )

    assert len(settings.exporters) == 1
    file_exp = settings.exporters[0]
    _assert_file_exporter(file_exp, path="a/b/c/d")
    file_config = file_exp["file"]
    path_settings = file_config.get("path_settings")
    assert path_settings is not None
    if isinstance(path_settings, dict):
        assert path_settings.get("path_pattern") == "logs/mcp-agent-{unique_id}.jsonl"
        assert path_settings.get("unique_id") == "timestamp"
        assert path_settings.get("timestamp_format") == "%Y%m%d_%H%M%S"
    else:
        assert path_settings.path_pattern == "logs/mcp-agent-{unique_id}.jsonl"
        assert path_settings.unique_id == "timestamp"
        assert path_settings.timestamp_format == "%Y%m%d_%H%M%S"


def test_v3_console_exporter_empty_dict():
    """Test key-discriminated console exporter with empty dict (no extra settings needed)."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[{"console": {}}],
    )

    assert len(settings.exporters) == 1
    _assert_console_exporter(settings.exporters[0])


# ============================================================================
# Cross-Version Compatibility Tests
# ============================================================================


def test_mixed_v1_and_v3_string_and_dict():
    """Test mixing string exporters with key-discriminated dict syntax in the same config."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            "console",  # String exporter
            {"file": {"path": "/tmp/trace.jsonl"}},  # Key-discriminated dict
        ],
    )

    assert len(settings.exporters) == 2
    _assert_console_exporter(settings.exporters[0])
    _assert_file_exporter(settings.exporters[1], path="/tmp/trace.jsonl")


def test_v2_to_v3_conversion():
    """Test that type-discriminated format is automatically converted to key-discriminated internal format."""
    v2_settings = OpenTelemetrySettings(
        enabled=True,
        exporters=[
            {"type": "console"},
            {
                "type": "otlp",
                "endpoint": "http://collector:4318",
                "headers": {"Auth": "Bearer xyz"},
            },
        ],
    )

    assert len(v2_settings.exporters) == 2
    _assert_console_exporter(v2_settings.exporters[0])
    _assert_otlp_exporter(
        v2_settings.exporters[1],
        endpoint="http://collector:4318",
        headers={"Auth": "Bearer xyz"},
    )


def test_v1_legacy_fields_removed_after_finalization():
    """Test that legacy top-level fields are removed from the model after conversion."""
    settings = OpenTelemetrySettings(
        enabled=True,
        exporters=["file"],
        path="/tmp/trace.jsonl",
    )

    # Legacy fields should be removed after finalization
    assert not hasattr(settings, "path")
    assert not hasattr(settings, "path_settings")


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_unsupported_exporter_type_raises():
    """Test that unsupported exporter types raise ValidationError from Pydantic."""
    with pytest.raises(ValidationError):
        OpenTelemetrySettings(exporters=["console", "invalid_exporter"])


def test_invalid_exporter_format_raises():
    """Test that invalid exporter formats raise ValueError."""
    with pytest.raises(
        ValidationError, match="OpenTelemetry exporters must be strings"
    ):
        OpenTelemetrySettings(
            exporters=[{"foo": "bar", "baz": "qux"}]
        )  # Multi-key dict


def test_invalid_dict_exporter_with_multi_keys_raises():
    """Test that key-discriminated dict exporters with multiple keys raise ValueError."""
    with pytest.raises(
        ValidationError, match="OpenTelemetry exporters must be strings"
    ):
        OpenTelemetrySettings(
            exporters=[
                {"console": {}, "file": {}}  # Invalid: two keys in one dict
            ]
        )


# ============================================================================
# Integration Tests with Full Settings
# ============================================================================


def test_settings_default_construction():
    """Test default Settings construction uses typed exporters."""
    settings = Settings()

    assert isinstance(settings.otel, OpenTelemetrySettings)
    assert isinstance(settings.otel.exporters, list)


def test_v1_full_config_via_settings():
    """Test string exporter config loaded via full Settings model."""
    settings = Settings(
        otel={
            "enabled": True,
            "exporters": ["console", "otlp"],
            "otlp_settings": {"endpoint": "http://collector:4318/v1/traces"},
        }
    )

    assert settings.otel.enabled is True
    assert len(settings.otel.exporters) == 2
    _assert_console_exporter(settings.otel.exporters[0])
    _assert_otlp_exporter(
        settings.otel.exporters[1], endpoint="http://collector:4318/v1/traces"
    )


def test_v2_full_config_via_settings():
    """Test type-discriminated config loaded via full Settings model."""
    settings = Settings(
        otel={
            "enabled": True,
            "exporters": [
                {"type": "console"},
                {"type": "file", "path": "/tmp/trace.jsonl"},
            ],
            "service_name": "TestApp",
        }
    )

    assert settings.otel.enabled is True
    assert settings.otel.service_name == "TestApp"
    assert len(settings.otel.exporters) == 2
    _assert_console_exporter(settings.otel.exporters[0])
    _assert_file_exporter(settings.otel.exporters[1], path="/tmp/trace.jsonl")


def test_v3_full_config_via_settings():
    """Test key-discriminated config loaded via full Settings model."""
    settings = Settings(
        otel={
            "enabled": True,
            "exporters": [
                {"console": {}},
                {"otlp": {"endpoint": "https://collector.example.com:4318"}},
            ],
            "service_name": "V3App",
            "sample_rate": 0.5,
        }
    )

    assert settings.otel.enabled is True
    assert settings.otel.service_name == "V3App"
    assert settings.otel.sample_rate == 0.5
    assert len(settings.otel.exporters) == 2
    _assert_console_exporter(settings.otel.exporters[0])
    _assert_otlp_exporter(
        settings.otel.exporters[1], endpoint="https://collector.example.com:4318"
    )


def test_merge_otel_exporters_from_config_and_secrets():
    """Test that OTEL exporters from config.yaml and secrets.yaml are merged together."""

    # Simulate config.yaml with one OTLP exporter (public endpoint)
    config_data = {
        "otel": {
            "exporters": [
                {
                    "otlp": {
                        "endpoint": "https://us.cloud.langfuse.com/api/public/otel/v1/traces",
                        "headers": {"Authorization": "Basic AUTH_STRING"},
                    }
                }
            ]
        }
    }

    # Simulate secrets.yaml with another OTLP exporter (secret endpoint)
    secrets_data = {
        "otel": {
            "enabled": True,
            "exporters": [{"otlp": {"endpoint": "https://some-other-otel-exporter"}}],
        }
    }

    # Manually perform deep merge as get_settings does internally
    def deep_merge(base: dict, update: dict, path: tuple = ()) -> dict:
        """Recursively merge two dictionaries, preserving nested structures.

        Special handling for 'exporters' lists under 'otel' key:
        - Concatenates lists instead of replacing them
        - Allows combining exporters from config and secrets files
        """
        merged = base.copy()
        for key, value in update.items():
            current_path = path + (key,)
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = deep_merge(merged[key], value, current_path)
            elif (
                key in merged
                and isinstance(merged[key], list)
                and isinstance(value, list)
                and current_path == ("otel", "exporters")
            ):
                # Concatenate exporters lists from config and secrets
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    merged = deep_merge(config_data, secrets_data)
    settings = Settings(**merged)

    # Verify both exporters are present
    assert settings.otel.enabled is True
    assert len(settings.otel.exporters) == 2

    # Verify first exporter (from config.yaml)
    _assert_otlp_exporter(
        settings.otel.exporters[0],
        endpoint="https://us.cloud.langfuse.com/api/public/otel/v1/traces",
        headers={"Authorization": "Basic AUTH_STRING"},
    )

    # Verify second exporter (from secrets.yaml)
    _assert_otlp_exporter(
        settings.otel.exporters[1], endpoint="https://some-other-otel-exporter"
    )


def test_merge_non_otel_lists_are_replaced_not_concatenated():
    """Test that non-OTEL lists are replaced, not concatenated (default behavior)."""

    # Manually perform deep merge as get_settings does internally
    def deep_merge(base: dict, update: dict, path: tuple = ()) -> dict:
        """Recursively merge two dictionaries, preserving nested structures.

        Special handling for 'exporters' lists under 'otel' key:
        - Concatenates lists instead of replacing them
        - Allows combining exporters from config and secrets files
        """
        merged = base.copy()
        for key, value in update.items():
            current_path = path + (key,)
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = deep_merge(merged[key], value, current_path)
            elif (
                key in merged
                and isinstance(merged[key], list)
                and isinstance(value, list)
                and current_path == ("otel", "exporters")
            ):
                # Concatenate exporters lists from config and secrets
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    # Test with logger.transports (should be replaced, not concatenated)
    config_data = {"logger": {"transports": ["console", "file"]}}
    secrets_data = {"logger": {"transports": ["http"]}}
    merged = deep_merge(config_data, secrets_data)
    # Should be replaced, not concatenated
    assert merged["logger"]["transports"] == ["http"]
    assert len(merged["logger"]["transports"]) == 1

    # Test with mcp.servers (dict, should be merged)
    config_data = {
        "mcp": {"servers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}}
    }
    secrets_data = {
        "mcp": {
            "servers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                }
            }
        }
    }
    merged = deep_merge(config_data, secrets_data)
    # Both servers should be present (dicts are merged)
    assert "fetch" in merged["mcp"]["servers"]
    assert "filesystem" in merged["mcp"]["servers"]

    # Test with a nested list that's NOT otel.exporters (should be replaced)
    config_data = {"agents": {"search_paths": [".claude/agents", "~/.claude/agents"]}}
    secrets_data = {"agents": {"search_paths": [".mcp-agent/agents"]}}
    merged = deep_merge(config_data, secrets_data)
    # Should be replaced, not concatenated
    assert merged["agents"]["search_paths"] == [".mcp-agent/agents"]
    assert len(merged["agents"]["search_paths"]) == 1
