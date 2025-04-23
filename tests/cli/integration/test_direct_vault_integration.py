"""Integration tests for DirectVaultSecretsApiClient.

These tests require a real Vault instance.
"""

import os
import pytest
import uuid
from pathlib import Path

from mcp_agent_cloud.secrets.direct_vault_client import DirectVaultSecretsApiClient
from mcp_agent_cloud.secrets.constants import SecretType


# Mark all tests in this module as requiring Vault
pytestmark = pytest.mark.vault_integration


@pytest.fixture
def vault_client():
    """Create a DirectVaultSecretsApiClient connected to a real Vault instance."""
    # Skip tests if Vault credentials are not available
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    
    if not vault_addr or not vault_token:
        pytest.skip("VAULT_ADDR and VAULT_TOKEN environment variables required")
    
    return DirectVaultSecretsApiClient(
        vault_addr=vault_addr,
        vault_token=vault_token
    )


@pytest.mark.asyncio
async def test_create_and_get_secret(vault_client):
    """Test creating and retrieving a secret."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.secret.{test_id}"
    secret_value = f"test-value-{test_id}"
    
    # Create a developer secret
    handle = await vault_client.create_secret(
        name=secret_name,
        type_=SecretType.DEVELOPER,
        value=secret_value
    )
    
    # Verify handle format
    assert handle.startswith(vault_client.DEV_HANDLE_PREFIX)
    
    try:
        # Retrieve the secret value
        retrieved_value = await vault_client.get_secret_value(handle)
        
        # Verify the value matches
        assert retrieved_value == secret_value
    finally:
        # Clean up (best effort)
        try:
            # Delete the secret (would need to implement delete method)
            # await vault_client.delete_secret(handle)
            pass
        except Exception:
            pass


@pytest.mark.asyncio
async def test_update_secret_value(vault_client):
    """Test updating a secret's value."""
    # Create a unique test name to avoid collisions
    test_id = str(uuid.uuid4())
    secret_name = f"test.user_secret.{test_id}"
    
    # Create a user secret (no initial value)
    handle = await vault_client.create_secret(
        name=secret_name,
        type_=SecretType.USER
    )
    
    # Verify handle format
    assert handle.startswith(vault_client.USR_HANDLE_PREFIX)
    
    try:
        # Set a value for the user secret
        new_value = f"user-value-{test_id}"
        await vault_client.set_secret_value(handle, new_value)
        
        # Retrieve the secret value
        retrieved_value = await vault_client.get_secret_value(handle)
        
        # Verify the value matches
        assert retrieved_value == new_value
    finally:
        # Clean up (best effort)
        try:
            # Delete the secret (would need to implement delete method)
            # await vault_client.delete_secret(handle)
            pass
        except Exception:
            pass