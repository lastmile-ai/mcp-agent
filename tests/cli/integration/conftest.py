"""Common fixtures for integration tests.

This module provides fixtures that can be used across all integration tests,
especially for handling API connectivity in either mock or real modes.
"""

import os
import pytest
from pathlib import Path

from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.mock_client import MockSecretsClient
from tests.fixtures.api_test_utils import setup_api_for_testing, APIMode


# Base path for realistic test fixtures
FIXTURES_BASE = Path(__file__).parent.parent / "fixtures" / "realistic_mcp_configs"


@pytest.fixture(scope="module")
def mock_api_credentials():
    """Mock API credentials that don't require a real connection."""
    return "http://mock-api-server.local", "mock-test-token"


@pytest.fixture(scope="module")
def real_api_credentials():
    """Real API credentials for tests that need a real connection.
    
    This requires a running web app with API access.
    """
    try:
        return setup_api_for_testing(APIMode.AUTO)
    except RuntimeError as e:
        pytest.skip(f"Skipping test requiring real API: {str(e)}")


@pytest.fixture(scope="function")
def mock_secrets_client():
    """Creates a mock secrets client for testing without API dependencies."""
    return MockSecretsClient(
        api_url="http://mock-api-server.local",
        api_token="mock-test-token"
    )


@pytest.fixture(scope="function")
def real_secrets_client():
    """Creates a real API secrets client for testing.
    
    Tests using this fixture will be skipped if the API is not available.
    Use this only for tests that specifically need to verify real API interaction.
    """
    try:
        api_url, api_token = setup_api_for_testing(APIMode.AUTO)
        return SecretsClient(
            api_url=api_url,
            api_token=api_token
        )
    except RuntimeError as e:
        pytest.skip(f"Skipping test with real API: {str(e)}")


@pytest.fixture(scope="function")
def setup_test_env_vars():
    """Set up and tear down environment variables needed for secret tests."""
    # Store original environment
    original_env = {}
    for var in [
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", 
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
        "DB_USER", "DB_PASSWORD"
    ]:
        original_env[var] = os.environ.get(var)
    
    # Set test values
    os.environ.update({
        "OPENAI_API_KEY": "sk-test-openai-key",
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "AWS_ACCESS_KEY_ID": "AKIATESTKEY12345678",
        "AWS_SECRET_ACCESS_KEY": "test-aws-secret-key",
        "DB_USER": "testuser",
        "DB_PASSWORD": "testpassword"
    })
    
    yield
    
    # Restore original environment
    for var, value in original_env.items():
        if value is None:
            if var in os.environ:
                del os.environ[var]
        else:
            os.environ[var] = value