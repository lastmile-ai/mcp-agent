"""pytest configuration for MCP Agent Cloud SDK tests."""

import os
import pytest
from typing import Any, Dict, Generator

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
        }
    }

@pytest.fixture
def sample_secrets_config() -> Dict[str, Any]:
    """Return a sample secrets configuration."""
    return {
        "$schema": "../../../../mcp-agent/schema/mcp-agent.config.schema.json",
        "server": {
            "bedrock": {
                "api_key": "!developer_secret ${oc.env:MCP_BEDROCK_API_KEY}",
                "user_access_key": "!user_secret"
            }
        }
    }


@pytest.fixture
def sample_config_yaml(sample_config: Dict[str, Any], tmp_path) -> str:
    """Create a sample config YAML file."""
    import yaml
    
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(sample_config, f)
    
    return str(config_path)


@pytest.fixture
def sample_secrets_yaml(sample_secrets_config: Dict[str, Any], tmp_path) -> str:
    """Create a sample secrets YAML file."""
    import yaml
    
    secrets_path = tmp_path / "test_secrets.yaml"
    with open(secrets_path, "w") as f:
        yaml.dump(sample_secrets_config, f)
    
    return str(secrets_path)