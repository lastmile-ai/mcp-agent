"""Integration tests for the SecretsClient with a real API.

These tests verify that the SecretsClient can correctly interact with
a real Secrets API service. They require a running web app instance.

IMPORTANT: These tests require the web app to have properly generated
proto files for the secrets service. The current error appears to be:

  Module not found: Can't resolve '@mcpac/proto/mcpac/api/secrets/v1/secrets_api_service_pb'

If you're seeing a 500 error from the API, this may be the cause.

To run these tests successfully:
1. Check that the proto files are properly generated:
   - Make sure idl/proto-mcpac/mcpac/api/secrets/v1/ exists and has proto files
   - Run any necessary code generation steps for the proto files

2. Start the web app: cd www && pnpm run webdev

3. Run the tests: pytest -m integration -v
"""

import uuid

import pytest
from mcp_agent_cloud.core.constants import SECRET_ID_PATTERN, SecretType

# Mark all tests in this module with the integration marker
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_create_and_get_real_secret(real_secrets_client):
    """Test creating and retrieving a secret via the real API."""
    # Create a unique test name
    test_id = str(uuid.uuid4().hex[:8])
    secret_name = f"test.api.{test_id}"
    secret_value = f"test-value-{test_id}"

    # Create a developer secret
    handle = await real_secrets_client.create_secret(
        name=secret_name, secret_type=SecretType.DEVELOPER, value=secret_value
    )

    # Verify the handle is a standard UUID
    assert SECRET_ID_PATTERN.match(handle), (
        f"Handle format '{handle}' doesn't match expected UUID pattern"
    )
    print(f"Created secret with handle: {handle}")

    try:
        # Retrieve the secret value
        retrieved_value = await real_secrets_client.get_secret_value(handle)

        # Verify it matches what we stored
        assert retrieved_value == secret_value, (
            f"Retrieved value '{retrieved_value}' doesn't match '{secret_value}'"
        )

    finally:
        # Clean up
        try:
            deleted_id = await real_secrets_client.delete_secret(handle)
            assert deleted_id == handle, (
                f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
            )
            print(f"Deleted test secret: {handle}")
        except Exception as e:
            print(f"Warning: Failed to delete test secret {handle}: {e}")


@pytest.mark.asyncio
async def test_update_real_secret_value(real_secrets_client):
    """Test updating a secret's value via the real API."""
    # Create a unique test name
    test_id = str(uuid.uuid4().hex[:8])
    secret_name = f"test.update.{test_id}"
    original_value = f"original-value-{test_id}"
    updated_value = f"updated-value-{test_id}"

    # Create a developer secret with initial value
    handle = await real_secrets_client.create_secret(
        name=secret_name,
        secret_type=SecretType.DEVELOPER,
        value=original_value,
    )

    try:
        # Update the secret value
        success = await real_secrets_client.set_secret_value(handle, updated_value)
        assert success is True, "set_secret_value operation failed"

        # Verify the value was updated
        retrieved_value = await real_secrets_client.get_secret_value(handle)
        assert retrieved_value == updated_value, (
            f"Retrieved value '{retrieved_value}' doesn't match updated value '{updated_value}'"
        )

    finally:
        # Clean up
        try:
            deleted_id = await real_secrets_client.delete_secret(handle)
            assert deleted_id == handle, (
                f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
            )
            print(f"Deleted test secret: {handle}")
        except Exception as e:
            print(f"Warning: Failed to delete test secret {handle}: {e}")


@pytest.mark.asyncio
async def test_list_real_secrets(real_secrets_client):
    """Test listing secrets via the real API."""
    # Create unique test secrets
    test_id = str(uuid.uuid4().hex[:8])
    prefix = f"test.list.{test_id}"

    # Create two secrets with the same prefix for filtering
    handles = []
    for i in range(2):
        name = f"{prefix}.{i}"
        value = f"value-{i}-{test_id}"

        handle = await real_secrets_client.create_secret(
            name=name, secret_type=SecretType.DEVELOPER, value=value
        )
        handles.append(handle)

    try:
        # List secrets with our test prefix
        secrets = await real_secrets_client.list_secrets(name_filter=prefix)

        # Verify we can find our test secrets
        found_names = [s.get("name") for s in secrets]
        for i in range(2):
            expected_name = f"{prefix}.{i}"
            assert expected_name in found_names, (
                f"Expected to find secret {expected_name} in results"
            )

    finally:
        # Clean up - delete the test secrets
        for handle in handles:
            try:
                deleted_id = await real_secrets_client.delete_secret(handle)
                assert deleted_id == handle, (
                    f"Deleted secret ID {deleted_id} doesn't match handle {handle}"
                )
                print(f"Deleted test secret: {handle}")
            except Exception as e:
                print(f"Warning: Failed to delete test secret {handle}: {e}")
