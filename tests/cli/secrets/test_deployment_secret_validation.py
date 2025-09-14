"""Tests for raw secret validation in the new workflow."""

from unittest.mock import AsyncMock

import pytest
from mcp_agent.cli.core.constants import UUID_PREFIX, SecretType
from mcp_agent.cli.secrets.api_client import SecretsClient
from mcp_agent.cli.secrets.processor import transform_config_recursive
from mcp_agent.cli.secrets.yaml_tags import DeveloperSecret, UserSecret


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock(spec=SecretsClient)

    # Configure create_secret to return UUIDs
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a deterministic UUID-like string based on name
        return f"{UUID_PREFIX}{name.replace('.', '-')}-uuid"

    client.create_secret.side_effect = mock_create_secret
    return client


@pytest.mark.asyncio
async def test_raw_secret_with_empty_value_skipped(mock_secrets_client):
    """Test that raw secrets with empty values are skipped."""
    # Create config with empty secret value
    config = {"server": {"api_key": ""}}

    # Empty secret should be skipped, not raise an error
    result = await transform_config_recursive(
        config, mock_secrets_client, non_interactive=True
    )

    # The secret should be skipped, so the key shouldn't be in the result
    assert "server" not in result


@pytest.mark.asyncio
async def test_raw_secret_with_none_value_skipped(mock_secrets_client):
    """Test that raw secrets with None values are skipped."""
    # Create config with None secret value
    config = {"server": {"api_key": None}}

    # None secret should be skipped, not processed as a secret
    result = await transform_config_recursive(
        config, mock_secrets_client, non_interactive=True
    )

    # The None value should be skipped
    assert "server" not in result

    # Verify create_secret was NOT called for None values
    mock_secrets_client.create_secret.assert_not_called()


@pytest.mark.asyncio
async def test_tagged_secrets_rejected_in_input(mock_secrets_client):
    """Test that tagged secrets in input are rejected with clear error."""
    # Create a developer secret tag (this should not be in input anymore)
    dev_secret = DeveloperSecret("some-value")
    user_secret = UserSecret()

    # Attempt to transform the tagged secret - should be rejected
    with pytest.raises(
        ValueError,
        match="Input secrets config at .* contains secret tag. Input should contain raw secrets, not tags.",
    ):
        await transform_config_recursive(
            dev_secret, mock_secrets_client, "server.api_key", non_interactive=True
        )

    with pytest.raises(
        ValueError,
        match="Input secrets config at .* contains secret tag. Input should contain raw secrets, not tags.",
    ):
        await transform_config_recursive(
            user_secret, mock_secrets_client, "server.api_key", non_interactive=True
        )


@pytest.mark.asyncio
async def test_valid_raw_secret_processed(mock_secrets_client):
    """Test that valid raw secrets are processed correctly."""
    # Create config with valid raw secret value
    config = {"server": {"api_key": "my-secret-key-value"}}

    # Process the config in non-interactive mode
    result = await transform_config_recursive(
        config, mock_secrets_client, non_interactive=True
    )

    # Verify the secret was transformed to a handle
    assert "server" in result
    assert "api_key" in result["server"]
    assert isinstance(result["server"]["api_key"], str)
    assert result["server"]["api_key"].startswith(UUID_PREFIX)

    # Verify create_secret was called
    mock_secrets_client.create_secret.assert_called_once()
    _args, kwargs = mock_secrets_client.create_secret.call_args
    assert kwargs["name"] == "server.api_key"
    assert kwargs["secret_type"] == SecretType.DEVELOPER
    assert kwargs["value"] == "my-secret-key-value"
