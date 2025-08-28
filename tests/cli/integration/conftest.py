"""Common fixtures for integration tests.

This module provides fixtures that can be used across all integration tests,
especially for handling API connectivity in either mock or real modes.
"""

import os
from pathlib import Path

import pytest
from mcp_agent.cli.secrets.api_client import SecretsClient
from mcp_agent.cli.secrets.mock_client import MockSecretsClient

from ..fixtures.api_test_utils import APIMode, setup_api_for_testing

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
        api_url="http://mock-api-server.local", api_key="mock-test-token"
    )


@pytest.fixture(scope="function")
def real_secrets_client():
    """Creates a real API secrets client for testing.

    Tests using this fixture will be skipped if the API is not available.
    Use this only for tests that specifically need to verify real API interaction.
    """
    import httpx

    try:
        # First check if the health endpoint is working
        try:
            response = httpx.get("http://localhost:3000/api/health", timeout=2.0)
            # Test with the actual token
            try:
                # Get the API token from environment
                api_token = os.environ.get("MCP_API_KEY")
                if not api_token:
                    from ..utils.jwt_generator import generate_jwt

                    # Generate a test token
                    nextauth_secret = os.environ.get(
                        "NEXTAUTH_SECRET", "testsecretfortestinglocalapidevelopmentonly"
                    )
                    test_user_id = f"test-user-{os.getpid()}"
                    api_token = generate_jwt(
                        user_id=test_user_id,
                        email="test@example.com",
                        api_token=True,
                        prefix=True,
                        nextauth_secret=nextauth_secret,
                    )
                    print(
                        f"Generated test API token for user {test_user_id}: {api_token[:20]}...{api_token[-10:]}"
                    )
                    os.environ["MCP_API_KEY"] = api_token

                secrets_response = httpx.post(
                    "http://localhost:3000/api/secrets/create_secret",
                    json={"name": "test", "type": "dev", "value": "test"},
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=2.0,
                )
                if "Error decoding API token" in secrets_response.text:
                    pytest.skip(
                        "API token validation error. "
                        "The test token is not valid for the running web app. "
                        "Please provide a valid token for this environment."
                    )
            except Exception:
                # Ignore connection errors here
                pass

            if response.status_code == 500:
                # Try to detect the specific proto error
                if "Can't resolve '@mcpac/proto/mcpac/api/secrets" in response.text:
                    pytest.skip(
                        "API is returning 500 error due to missing proto files. "
                        "Make sure the proto files are generated properly."
                    )
                else:
                    pytest.skip(
                        f"API health endpoint is returning 500 error: {response.status_code}"
                    )
        except Exception:
            pass  # Let the regular API setup handle connection errors

        # Proceed with normal API setup
        api_url, api_token = setup_api_for_testing(APIMode.AUTO)
        return SecretsClient(api_url=api_url, api_key=api_token)
    except RuntimeError as e:
        pytest.skip(f"Skipping test with real API: {str(e)}")


@pytest.fixture(scope="function")
def setup_test_env_vars():
    """Set up and tear down environment variables needed for secret tests."""
    # Store original environment
    original_env = {}
    for var in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "DB_USER",
        "DB_PASSWORD",
    ]:
        original_env[var] = os.environ.get(var)

    # Set test values
    os.environ.update(
        {
            "OPENAI_API_KEY": "sk-test-openai-key",
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
            "AWS_ACCESS_KEY_ID": "AKIATESTKEY12345678",
            "AWS_SECRET_ACCESS_KEY": "test-aws-secret-key",
            "DB_USER": "testuser",
            "DB_PASSWORD": "testpassword",
        }
    )

    yield

    # Restore original environment
    for var, value in original_env.items():
        if value is None:
            if var in os.environ:
                del os.environ[var]
        else:
            os.environ[var] = value
