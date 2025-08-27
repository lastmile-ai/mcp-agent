"""pytest configuration for MCP Agent Cloud SDK tests."""

import os
from typing import Any, Dict

import pytest
from mcp_agent.cli.core.constants import (
    MCP_CONFIG_FILENAME,
    MCP_SECRETS_FILENAME,
)


# Set environment variables needed for tests
def pytest_configure(config):
    """Configure pytest environment."""
    # API endpoint configuration
    os.environ.setdefault("MCP_API_BASE_URL", "http://localhost:3000/api")
    os.environ.setdefault("MCP_API_KEY", "test-token")
    os.environ.setdefault("MCP_VERBOSE", "true")


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Return a sample configuration without secrets."""
    return {
        "$schema": "../../../../mcp-agent/schema/mcp-agent.config.schema.json",
        "server": {
            "bedrock": {
                "default_model": "anthropic.claude-3-haiku-20240307-v1:0",
            }
        },
    }


@pytest.fixture
def sample_secrets_config() -> Dict[str, Any]:
    """Return a sample secrets configuration."""
    return {
        "$schema": "../../../../mcp-agent/schema/mcp-agent.config.schema.json",
        "server": {
            "bedrock": {
                "api_key": "!developer_secret MCP_BEDROCK_API_KEY",
                "user_access_key": "!user_secret",
            }
        },
    }


@pytest.fixture
def sample_config_dir(sample_config: Dict[str, Any]) -> str:
    """Create a sample config YAML file in a temp directory."""
    import tempfile
    from pathlib import Path

    import yaml

    test_dir = Path(tempfile.mkdtemp())

    config_path = test_dir / MCP_CONFIG_FILENAME
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(sample_config, f)

    return test_dir


@pytest.fixture
def sample_secrets_config_dir(
    sample_config_dir: str, sample_secrets_config: Dict[str, Any]
) -> str:
    """Create a sample secrets YAML file in the config directory."""
    import yaml

    secrets_path = sample_config_dir / MCP_SECRETS_FILENAME
    with open(secrets_path, "w", encoding="utf-8") as f:
        yaml.dump(sample_secrets_config, f)

    return sample_config_dir
