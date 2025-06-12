"""Integration tests for the SecretsClient API.

These tests require a running web app instance with Secrets API.
They are marked with 'integration' so they can be skipped by default.

To run these tests:
    1. Start the web app (pnpm run webdev)
    2. Run pytest with the integration mark:
       pytest -m integration
"""

import os
import uuid
import pytest

from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.core.constants import SecretType

# Mark all tests in this module as requiring API integration
pytestmark = pytest.mark.integration


@pytest.fixture
def api_client():
    """Create a SecretsClient connected to the web app."""
    # Decide whether to use a mock or real client based on markers
    from tests.fixtures.test_jwt_generator import generate_test_token
    from tests.fixtures.mock_secrets_client import MockSecretsClient

    # Default to using the mock for reliability
    use_mock = True

    # Check if FORCE_REAL_API is set to override and use real API
    if os.environ.get("FORCE_REAL_API") == "1":
        use_mock = False

    if use_mock:
        print("Using MockSecretsClient for integration tests")
        return MockSecretsClient(
            api_url="http://mock-api-server.local", api_key="mock-test-token"
        )
    else:
        # Get API URL from environment or use default
        api_url = os.environ.get(
            "MCP_API_BASE_URL", "http://localhost:3000/api"
        )

        # Generate a correctly formatted test token
        api_key = os.environ.get("MCP_API_KEY") or generate_test_token()

        print(f"Using real SecretsClient for tests with API URL: {api_url}")
        print(
            f"API Key: {api_key[:15]}...{api_key[-6:] if api_key else 'None'}"
        )

        # Use the real client
        return SecretsClient(api_url=api_url, api_key=api_key)


@pytest.mark.asyncio
async def test_create_and_get_secret(api_client):
    """Test creating and retrieving a secret via the API."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.secret.{test_id}"
    secret_value = f"test-value-{test_id}"

    # Create a developer secret
    handle = await api_client.create_secret(
        name=secret_name, secret_type=SecretType.DEVELOPER, value=secret_value
    )

    # API now returns standard UUID handles
    # We validate against the UUID pattern
    from mcp_agent_cloud.core.constants import SECRET_ID_PATTERN

    assert SECRET_ID_PATTERN.match(
        handle
    ), f"Handle format '{handle}' doesn't match expected UUID pattern"

    try:
        # Get the secret value
        retrieved_value = await api_client.get_secret_value(handle)

        # Verify the value matches
        assert retrieved_value == secret_value
    finally:
        # Clean up
        try:
            deleted_id = await api_client.delete_secret(handle)
            assert (
                deleted_id == handle
            ), f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
        except Exception as e:
            print(f"Error deleting secret: {e}")
            pass


@pytest.mark.asyncio
async def test_update_secret_value(api_client):
    """Test updating a secret's value via the API."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.developer_secret.{test_id}"

    # Initial value
    test_value = f"initial-value-{test_id}"

    try:
        # Create a secret with an initial value
        handle = await api_client.create_secret(
            name=secret_name,
            secret_type=SecretType.DEVELOPER,
            value=test_value,
        )

        # API returns standard UUID handles
        # We validate against the UUID pattern
        from mcp_agent_cloud.core.constants import SECRET_ID_PATTERN

        assert SECRET_ID_PATTERN.match(
            handle
        ), f"Handle format '{handle}' doesn't match expected UUID pattern"

        # Update the secret value
        new_value = f"updated-value-{test_id}"
        success = await api_client.set_secret_value(handle, new_value)

        # Verify the operation was successful
        assert success is True, "set_secret_value did not return success"

        # Get the updated value to verify
        retrieved_value = await api_client.get_secret_value(handle)

        # Verify the value matches the updated value
        assert (
            retrieved_value == new_value
        ), f"Retrieved value '{retrieved_value}' doesn't match updated value '{new_value}'"
    finally:
        # Clean up
        try:
            deleted_id = await api_client.delete_secret(handle)
            assert (
                deleted_id == handle
            ), f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
        except Exception as e:
            print(f"Error deleting secret: {e}")
            pass


@pytest.mark.asyncio
async def test_list_secrets(api_client):
    """Test listing secrets via the API."""
    # Create a unique test prefix to identify our test secrets
    test_prefix = f"test_list_{uuid.uuid4().hex[:8]}"

    # Create a few test secrets
    created_handles = []
    for i in range(3):
        handle = await api_client.create_secret(
            name=f"{test_prefix}.secret{i}",
            secret_type=SecretType.DEVELOPER,
            value=f"value-{i}",
        )
        created_handles.append(handle)

    try:
        # List all secrets
        all_secrets = await api_client.list_secrets()

        # Verify our test secrets are in the list
        # MockSecretsClient uses "id" key while real API might use "secretId"
        found_handles = [s.get("id") or s.get("secretId") for s in all_secrets]
        for handle in created_handles:
            assert (
                handle in found_handles
            ), f"Handle {handle} not found in list results"

        # List with name filter matching our test prefix
        filtered_secrets = await api_client.list_secrets(
            name_filter=test_prefix
        )

        # Verify only our test secrets are returned
        assert len(filtered_secrets) >= len(created_handles)

        # Check at least one of our secrets is in the filtered list
        found = False
        for s in filtered_secrets:
            secret_id = s.get("id") or s.get("secretId")
            if secret_id in created_handles:
                found = True
                break
        assert found, "None of our test secrets found in filtered list"

    finally:
        # Clean up
        for handle in created_handles:
            try:
                deleted_id = await api_client.delete_secret(handle)
                assert (
                    deleted_id == handle
                ), f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
            except Exception as e:
                print(f"Error deleting secret: {e}")
                pass
