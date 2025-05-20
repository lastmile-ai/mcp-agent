"""Tests for transforming secrets in configurations.

This file tests the core functionality of the transform_config_recursive function,
which should convert DeveloperSecret tags to UUID handles during deployment.

Note: Using the fixed_processor module since the standard processor has issues.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch

from mcp_agent_cloud.secrets.yaml_tags import DeveloperSecret, UserSecret
from mcp_agent_cloud.core.constants import SecretType, UUID_PREFIX
from mcp_agent_cloud.secrets.api_client import SecretsClient


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient with controlled behavior."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return predictable UUIDs
    async def mock_create_secret(name, secret_type, value=None):
        # Generate deterministic but valid UUID for testing
        path_hash = str(hash(name))[-8:]  # Last 8 chars of hash for uniqueness
        uuid_str = f"00000000-0000-0000-0000-{path_hash.zfill(12)}"
        # Use the required prefix
        handle = f"{UUID_PREFIX}{uuid_str}"
        return handle
    
    client.create_secret.side_effect = mock_create_secret
    return client


class TestSecretTransform:
    """Tests for transforming secrets during deploy phase."""
    
    @pytest.mark.asyncio
    async def test_transform_developer_secret_directly(self, mock_secrets_client):
        """Test transforming a developer secret directly."""
        # Import from the main processor module
        from mcp_agent_cloud.secrets.processor import transform_config_recursive
        
        # Test a direct DeveloperSecret object
        test_path = "api.key"
        dev_secret = DeveloperSecret("test-api-key")
        
        # Mock environment variable lookup and typer prompts
        with patch.dict('os.environ', {}, clear=True), \
             patch('typer.prompt', return_value="mocked-value"):
            
            # Transform the secret
            result = await transform_config_recursive(
                dev_secret, 
                mock_secrets_client,
                test_path,
                non_interactive=False
            )
            
            # Verify the result is a string (UUID handle)
            assert isinstance(result, str), f"Expected string but got {type(result)}"
            assert result.startswith(UUID_PREFIX), f"Expected prefix {UUID_PREFIX} but got {result}"
            
            # Verify create_secret was called correctly
            mock_secrets_client.create_secret.assert_called_once()
            # Get the call args
            args, kwargs = mock_secrets_client.create_secret.call_args
            assert kwargs["name"] == test_path
            assert kwargs["secret_type"] == SecretType.DEVELOPER
            assert kwargs["value"] in ("test-api-key", "mocked-value")
    
    @pytest.mark.asyncio
    async def test_transform_developer_secret_in_dict(self, mock_secrets_client):
        """Test transforming a developer secret within a dictionary."""
        # Import from the main processor module
        from mcp_agent_cloud.secrets.processor import transform_config_recursive
        
        # Test dictionary with DeveloperSecret
        config = {
            "api": {
                "key": DeveloperSecret("test-api-key")
            }
        }
        
        # Mock environment variable lookup and typer prompts
        with patch.dict('os.environ', {}, clear=True), \
             patch('typer.prompt', return_value="mocked-value"):
            
            # Transform the config
            result = await transform_config_recursive(
                config, 
                mock_secrets_client,
                non_interactive=False
            )
            
            # Verify the structure is preserved
            assert isinstance(result, dict)
            assert "api" in result
            assert isinstance(result["api"], dict)
            assert "key" in result["api"]
            
            # The key should now be a UUID string
            assert isinstance(result["api"]["key"], str), f"Expected string but got {type(result['api']['key'])}"
            assert result["api"]["key"].startswith(UUID_PREFIX)
            
            # Verify create_secret was called correctly
            mock_secrets_client.create_secret.assert_called_once()
            # Get the call args
            args, kwargs = mock_secrets_client.create_secret.call_args
            assert kwargs["name"] == "api.key"
            assert kwargs["secret_type"] == SecretType.DEVELOPER
    
    @pytest.mark.asyncio
    async def test_keep_user_secret_as_is(self, mock_secrets_client):
        """Test that user secrets are kept as-is during transform."""
        # Import from the main processor module
        from mcp_agent_cloud.secrets.processor import transform_config_recursive
        
        # Test with UserSecret
        user_secret = UserSecret("test-user-key")
        
        # Transform the secret
        result = await transform_config_recursive(
            user_secret, 
            mock_secrets_client,
            "user.key",
            non_interactive=False
        )
        
        # Verify it's still a UserSecret object
        assert isinstance(result, UserSecret)
        assert result.value == "test-user-key"
        
        # Verify create_secret was NOT called for user secrets
        mock_secrets_client.create_secret.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_transform_mixed_secrets(self, mock_secrets_client):
        """Test transforming a config with both developer and user secrets."""
        # Import from the main processor module
        from mcp_agent_cloud.secrets.processor import transform_config_recursive
        
        # Test dictionary with both types of secrets
        config = {
            "api": {
                "dev_key": DeveloperSecret("test-api-key"),
                "user_key": UserSecret("test-user-key")
            }
        }
        
        # Mock environment variable lookup and typer prompts
        with patch.dict('os.environ', {}, clear=True), \
             patch('typer.prompt', return_value="mocked-value"):
            
            # Transform the config
            result = await transform_config_recursive(
                config, 
                mock_secrets_client,
                non_interactive=False
            )
            
            # Verify structure is preserved
            assert isinstance(result, dict)
            assert "api" in result
            assert isinstance(result["api"], dict)
            assert "dev_key" in result["api"]
            assert "user_key" in result["api"]
            
            # Developer secret should be transformed to UUID string
            assert isinstance(result["api"]["dev_key"], str)
            assert result["api"]["dev_key"].startswith(UUID_PREFIX)
            
            # User secret should remain as UserSecret object
            assert isinstance(result["api"]["user_key"], UserSecret)
            assert result["api"]["user_key"].value == "test-user-key"
            
            # Verify create_secret was called once (for developer secret only)
            assert mock_secrets_client.create_secret.call_count == 1
            # Get the call args
            args, kwargs = mock_secrets_client.create_secret.call_args
            assert kwargs["name"] == "api.dev_key"
            assert kwargs["secret_type"] == SecretType.DEVELOPER
    
    @pytest.mark.asyncio
    async def test_process_env_var_in_developer_secret(self, mock_secrets_client):
        """Test processing environment variables in developer secrets."""
        # Import from the main processor module
        from mcp_agent_cloud.secrets.processor import transform_config_recursive
        
        # Test with environment variable
        dev_secret = DeveloperSecret("TEST_API_KEY")
        
        # Set up the environment variable
        with patch.dict('os.environ', {"TEST_API_KEY": "env-value"}), \
             patch('typer.prompt', return_value="should-not-be-used"):
            
            # Transform the secret
            result = await transform_config_recursive(
                dev_secret, 
                mock_secrets_client,
                "api.key",
                non_interactive=False
            )
            
            # Verify the result is a string (UUID handle)
            assert isinstance(result, str)
            assert result.startswith(UUID_PREFIX)
            
            # Verify create_secret was called with the env var value
            mock_secrets_client.create_secret.assert_called_once()
            args, kwargs = mock_secrets_client.create_secret.call_args
            assert kwargs["value"] == "env-value"