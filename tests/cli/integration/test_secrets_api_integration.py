"""Integration tests for the SecretsClient API.

These tests require a running web app instance with Secrets API.
They are marked with 'integration' so they can be skipped by default.

To run these tests:
    1. Start the web app (pnpm run webdev)
    2. Run pytest with the integration mark:
       pytest -m integration
"""

import os
import pytest
import uuid

from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.constants import SecretType
from tests.fixtures.api_test_utils import setup_api_for_testing, APIMode

# Mark all tests in this module as requiring API integration
pytestmark = pytest.mark.integration


@pytest.fixture
def api_client():
    """Create a SecretsClient connected to the web app."""
    # Use the API test manager to set up the API
    api_url, api_token = setup_api_for_testing(APIMode.AUTO)
    
    return SecretsClient(
        api_url=api_url,
        api_token=api_token
    )


@pytest.mark.asyncio
async def test_create_and_get_secret(api_client):
    """Test creating and retrieving a secret via the API."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.secret.{test_id}"
    secret_value = f"test-value-{test_id}"
    
    # Create a developer secret
    handle = await api_client.create_secret(
        name=secret_name,
        secret_type=SecretType.DEVELOPER,
        value=secret_value
    )
    
    # Verify handle format
    assert handle.startswith("mcpac_dev_")
    
    try:
        # Retrieve the secret value
        retrieved_value = await api_client.get_secret_value(handle)
        
        # Verify the value matches
        assert retrieved_value == secret_value
    finally:
        # Clean up
        try:
            await api_client.delete_secret(handle)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_update_secret_value(api_client):
    """Test updating a secret's value via the API."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.user_secret.{test_id}"
    
    # Create a user secret (no initial value)
    handle = await api_client.create_secret(
        name=secret_name,
        secret_type=SecretType.USER
    )
    
    # Verify handle format
    assert handle.startswith("mcpac_usr_")
    
    try:
        # Set a value for the user secret
        new_value = f"user-value-{test_id}"
        await api_client.set_secret_value(handle, new_value)
        
        # Retrieve the secret value
        retrieved_value = await api_client.get_secret_value(handle)
        
        # Verify the value matches
        assert retrieved_value == new_value
    finally:
        # Clean up
        try:
            await api_client.delete_secret(handle)
        except Exception:
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
            value=f"value-{i}"
        )
        created_handles.append(handle)
    
    try:
        # List all secrets
        all_secrets = await api_client.list_secrets()
        
        # Verify our test secrets are in the list
        found_handles = [s.get("id") for s in all_secrets]
        for handle in created_handles:
            assert handle in found_handles
        
        # List with name filter matching our test prefix
        filtered_secrets = await api_client.list_secrets(name_filter=test_prefix)
        
        # Verify only our test secrets are returned
        assert len(filtered_secrets) >= len(created_handles)
        
        # Check at least one of our secrets is in the filtered list
        found = False
        for s in filtered_secrets:
            if s.get("id") in created_handles:
                found = True
                break
        assert found, "None of our test secrets found in filtered list"
        
    finally:
        # Clean up
        for handle in created_handles:
            try:
                await api_client.delete_secret(handle)
            except Exception:
                pass