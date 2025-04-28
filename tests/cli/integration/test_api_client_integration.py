"""Integration tests for the SecretsClient with a real API.

These tests verify that the SecretsClient can correctly interact with
a real Secrets API service. They require a running web app instance.

To run these tests:
1. Start the web app: cd www && pnpm run webdev
2. Run the tests: pytest -m "integration and api" -v
"""

import uuid
import pytest

from mcp_agent_cloud.secrets.constants import SecretType, HANDLE_PATTERN

# Mark all tests in this module with the integration and api markers
pytestmark = [pytest.mark.integration, pytest.mark.api]


@pytest.mark.asyncio
async def test_create_and_get_real_secret(real_secrets_client):
    """Test creating and retrieving a secret via the real API."""
    # Create a unique test name
    test_id = str(uuid.uuid4().hex[:8])
    secret_name = f"test.api.{test_id}"
    secret_value = f"test-value-{test_id}"
    
    # Create a developer secret
    handle = await real_secrets_client.create_secret(
        name=secret_name,
        secret_type=SecretType.DEVELOPER,
        value=secret_value
    )
    
    # Verify the handle format
    assert HANDLE_PATTERN.match(handle), f"Handle format '{handle}' doesn't match expected UUID pattern"
    print(f"Created secret with handle: {handle}")
    
    try:
        # Retrieve the secret value
        retrieved_value = await real_secrets_client.get_secret_value(handle)
        
        # Verify it matches what we stored
        assert retrieved_value == secret_value, f"Retrieved value '{retrieved_value}' doesn't match '{secret_value}'"
        
    finally:
        # Clean up - delete the secret
        try:
            await real_secrets_client.delete_secret(handle)
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
        value=original_value
    )
    
    try:
        # Update the secret value
        await real_secrets_client.set_secret_value(handle, updated_value)
        
        # Retrieve the updated value
        retrieved_value = await real_secrets_client.get_secret_value(handle)
        
        # Verify it matches the updated value
        assert retrieved_value == updated_value, \
            f"Retrieved value '{retrieved_value}' doesn't match updated value '{updated_value}'"
            
    finally:
        # Clean up - delete the secret
        try:
            await real_secrets_client.delete_secret(handle)
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
            name=name,
            secret_type=SecretType.DEVELOPER,
            value=value
        )
        handles.append(handle)
    
    try:
        # List secrets with our test prefix
        secrets = await real_secrets_client.list_secrets(name_filter=prefix)
        
        # Verify we can find our test secrets
        found_names = [s.get("name") for s in secrets]
        for i in range(2):
            expected_name = f"{prefix}.{i}"
            assert expected_name in found_names, f"Expected to find secret {expected_name} in results"
            
    finally:
        # Clean up - delete the test secrets
        for handle in handles:
            try:
                await real_secrets_client.delete_secret(handle)
                print(f"Deleted test secret: {handle}")
            except Exception as e:
                print(f"Warning: Failed to delete test secret {handle}: {e}")