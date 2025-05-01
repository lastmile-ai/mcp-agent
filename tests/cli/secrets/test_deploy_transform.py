"""Tests for secret transformation during deploy phase."""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, Mock
import yaml
from typing import Dict, Any

from mcp_agent_cloud.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    load_yaml_with_secrets,
)
from mcp_agent_cloud.core.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient

# TODO: Refactor architecture to eliminate circular imports between modules
# For now, import the entire module rather than specific functions
import mcp_agent_cloud.secrets.processor as processor_module


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return UUIDs
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a deterministic UUID-like string based on inputs
        if secret_type == SecretType.DEVELOPER:
            return f"12345678-abcd-1234-efgh-dev-{name.replace('.', '-')}"
        else:
            return f"87654321-wxyz-6789-abcd-usr-{name.replace('.', '-')}"
    
    client.create_secret.side_effect = mock_create_secret
    return client


# TRANSFORM RECURSIVE TESTS - Core of deploy functionality

@pytest.mark.asyncio
async def test_transform_config_recursive_developer_secret(mock_secrets_client, monkeypatch):
    """Test transforming a config with developer secrets."""
    # Mock the typer.prompt function to avoid actual prompting
    with patch("typer.prompt", return_value="mock-secret-value"):
        # Create a simple config with only developer secrets
        config = {
            "api": {
                "key": DeveloperSecret("dev-api-key")
            },
            "database": {
                "password": DeveloperSecret("dev-db-password")
            }
        }
        
        # Transform the config using module reference
        result = await processor_module.transform_config_recursive(config, mock_secrets_client)
        
        # Verify the result has string UUIDs instead of DeveloperSecret objects
        assert isinstance(result["api"]["key"], str)
        assert "12345678-abcd-1234-efgh-dev-api-key" in result["api"]["key"]
        
        assert isinstance(result["database"]["password"], str)
        assert "12345678-abcd-1234-efgh-dev-database-password" in result["database"]["password"]
        
        # Verify API was called for each developer secret
        assert mock_secrets_client.create_secret.call_count == 2
        
        # Check the API calls (we don't care about the exact order)
        api_key_call = None
        db_password_call = None
        
        for call in mock_secrets_client.create_secret.call_args_list:
            _, kwargs = call
            if kwargs["name"] == "api.key":
                api_key_call = kwargs
            elif kwargs["name"] == "database.password":
                db_password_call = kwargs
        
        # Check for api.key call
        assert api_key_call is not None
        assert api_key_call["secret_type"] == SecretType.DEVELOPER
        assert api_key_call["value"] == "mock-secret-value"
        
        # Check for database.password call
        assert db_password_call is not None
        assert db_password_call["secret_type"] == SecretType.DEVELOPER
        assert db_password_call["value"] == "mock-secret-value"


@pytest.mark.asyncio
async def test_transform_config_recursive_user_secret(mock_secrets_client):
    """Test transforming a config with user secrets - should remain unchanged during deploy."""
    # Create a config with only user secrets
    config = {
        "api": {
            "user_token": UserSecret("USER_TOKEN")
        },
        "database": {
            "user_password": UserSecret()  # Empty user secret
        }
    }
    
    # Transform the config for deploy (should keep user secrets as-is)
    result = await processor_module.transform_config_recursive(config, mock_secrets_client)
    
    # Verify user secrets are still UserSecret objects
    assert isinstance(result["api"]["user_token"], UserSecret)
    assert result["api"]["user_token"].value == "USER_TOKEN"
    
    assert isinstance(result["database"]["user_password"], UserSecret)
    assert result["database"]["user_password"].value is None
    
    # Verify no API calls were made for user secrets during deploy
    assert mock_secrets_client.create_secret.call_count == 0


@pytest.mark.asyncio
async def test_transform_config_recursive_mixed_secrets(mock_secrets_client):
    """Test transforming a config with both developer and user secrets."""
    # Create a complex config with both types of secrets
    config = {
        "api": {
            "key": DeveloperSecret("dev-api-key"),
            "user_token": UserSecret("USER_TOKEN")
        },
        "database": {
            "password": DeveloperSecret("dev-db-password"),
            "user_password": UserSecret()  # Empty user secret
        }
    }
    
    # Mock the typer.prompt function to avoid actual prompting
    with patch("typer.prompt", return_value="mock-secret-value"):
        # Transform the config
        result = await processor_module.transform_config_recursive(config, mock_secrets_client)
        
        # Verify the result - developer secrets should be UUIDs
        assert isinstance(result["api"]["key"], str)
        assert "12345678-abcd-1234-efgh-dev-api-key" in result["api"]["key"]
        
        assert isinstance(result["database"]["password"], str)
        assert "12345678-abcd-1234-efgh-dev-database-password" in result["database"]["password"]
        
        # User secrets should remain as UserSecret objects
        assert isinstance(result["api"]["user_token"], UserSecret)
        assert result["api"]["user_token"].value == "USER_TOKEN"
        
        assert isinstance(result["database"]["user_password"], UserSecret)
        assert result["database"]["user_password"].value is None
        
        # Verify API was called only for developer secrets
        assert mock_secrets_client.create_secret.call_count == 2


@pytest.mark.asyncio
async def test_transform_recursive_nested_structure(mock_secrets_client):
    """Test transforming a complex nested config structure with secrets."""
    # Create a deeply nested structure with various secret types
    config = {
        "server": {
            "providers": {
                "bedrock": {
                    "api_key": DeveloperSecret("dev-bedrock-key"),
                    "region": "us-west-2",  # Non-secret value
                },
                "openai": {
                    "api_key": UserSecret("USER_OPENAI_KEY"),
                    "org_id": "org-123",    # Non-secret value
                }
            },
            "list_example": [
                {"key": DeveloperSecret("list-item-0")},
                {"key": UserSecret("USER_LIST_ITEM")},
                "regular value",
                42
            ]
        }
    }
    
    # Mock the typer.prompt function to avoid actual prompting
    with patch("typer.prompt", return_value="mock-secret-value"):
        # Transform the config
        result = await processor_module.transform_config_recursive(config, mock_secrets_client)
        
        # Verify the result structure is preserved
        assert "server" in result
        assert "providers" in result["server"]
        assert "bedrock" in result["server"]["providers"]
        assert "openai" in result["server"]["providers"]
        assert "list_example" in result["server"]
        
        # Verify non-secret values are preserved as-is
        assert result["server"]["providers"]["bedrock"]["region"] == "us-west-2"
        assert result["server"]["providers"]["openai"]["org_id"] == "org-123"
        assert result["server"]["list_example"][2] == "regular value"
        assert result["server"]["list_example"][3] == 42
        
        # Verify developer secrets were transformed to UUIDs
        assert isinstance(result["server"]["providers"]["bedrock"]["api_key"], str)
        assert "12345678-abcd-1234-efgh-dev-server-providers-bedrock-api_key" in result["server"]["providers"]["bedrock"]["api_key"]
        
        assert isinstance(result["server"]["list_example"][0]["key"], str)
        assert "12345678-abcd-1234-efgh-dev-server-list_example[0]-key" in result["server"]["list_example"][0]["key"]
        
        # Verify user secrets remain as UserSecret objects
        assert isinstance(result["server"]["providers"]["openai"]["api_key"], UserSecret)
        assert result["server"]["providers"]["openai"]["api_key"].value == "USER_OPENAI_KEY"
        
        assert isinstance(result["server"]["list_example"][1]["key"], UserSecret)
        assert result["server"]["list_example"][1]["key"].value == "USER_LIST_ITEM"
        
        # Verify API was called only for developer secrets
        assert mock_secrets_client.create_secret.call_count == 2


# ENVIRONMENT VARIABLE RESOLUTION TESTS

@pytest.mark.asyncio
async def test_transform_config_recursive_with_env_vars(mock_secrets_client, monkeypatch):
    """Test environment variable resolution for secrets."""
    # Set test environment variables
    monkeypatch.setenv("BEDROCK_API_KEY", "env-bedrock-api-key")
    monkeypatch.setenv("DB_PASSWORD", "env-db-password")
    
    # Create config with env var names as values
    config = {
        "server": {
            "bedrock": {
                "api_key": DeveloperSecret("BEDROCK_API_KEY")  # Env var name
            }
        },
        "database": {
            "password": DeveloperSecret("DB_PASSWORD")  # Env var name
        }
    }
    
    # Transform the config (with a mock prompt as a fallback in case env vars don't work)
    with patch("typer.prompt", return_value="this-should-not-be-used"):
        result = await processor_module.transform_config_recursive(config, mock_secrets_client)
    
        # Verify API was called with resolved environment variable values
        assert mock_secrets_client.create_secret.call_count == 2
        
        # Check each call for correct env var resolution
        bedrock_api_key_call = None
        db_password_call = None
        
        for call in mock_secrets_client.create_secret.call_args_list:
            _, kwargs = call
            if kwargs["name"] == "server.bedrock.api_key":
                bedrock_api_key_call = kwargs
            elif kwargs["name"] == "database.password":
                db_password_call = kwargs
        
        # Verify that environment variable values were used
        assert bedrock_api_key_call is not None
        assert bedrock_api_key_call["value"] == "env-bedrock-api-key"  # Value from env var
        
        assert db_password_call is not None
        assert db_password_call["value"] == "env-db-password"  # Value from env var


@pytest.mark.asyncio
async def test_process_secrets_in_config_with_env_vars(mock_secrets_client, monkeypatch):
    """Test environment variable resolution in process_secrets_in_config."""
    # Set test environment variables
    monkeypatch.setenv("TEST_API_KEY", "env-api-key")
    monkeypatch.setenv("TEST_USER_SECRET", "env-user-secret")
    
    yaml_content = """
server:
  bedrock:
    api_key: !developer_secret TEST_API_KEY
    user_api_key: !user_secret TEST_USER_SECRET
"""
    
    # Process the YAML content with a fallback prompt mock in case env vars don't work
    with patch("typer.prompt", return_value="this-should-not-be-used"):
        result = await processor_module.process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=False)
        
        # The output should have developer_secret replaced with a handle
        # and user_secret kept as-is but with its value (env var name)
        assert "12345678-abcd-1234-efgh-dev-server-bedrock-api_key" in result
        assert "!user_secret" in result and "TEST_USER_SECRET" in result


# COMPREHENSIVE YAML PROCESSING TESTS

@pytest.mark.asyncio
async def test_process_secrets_in_config_comprehensive(mock_secrets_client):
    """Comprehensive test for process_secrets_in_config functionality."""
    yaml_content = """
# $schema: ...
server:
  bedrock:
    # Value comes from env var (in real usage)
    api_key: !developer_secret dev-api-key
    # Value collected during configure phase
    user_access_key: !user_secret USER_KEY
  
database:
  # Empty developer secret would be prompted for
  password: !developer_secret dev-db-password
  user_password: !user_secret

# Test complex nested structure
providers:
  list:
    - name: provider1
      key: !developer_secret provider1-key
    - name: provider2 
      key: !user_secret
"""
    
    # Mock the typer.prompt function to avoid actual prompting
    with patch("typer.prompt", return_value="mock-secret-value"):
        # Process the YAML content
        result = await processor_module.process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=False)
        
        # Developer secrets should be replaced with handles
        assert "12345678-abcd-1234-efgh-dev-server-bedrock-api_key" in result
        assert "12345678-abcd-1234-efgh-dev-database-password" in result
        assert "12345678-abcd-1234-efgh-dev-providers-list[0]-key" in result
        
        # User secrets should remain as tags
        assert "user_access_key: !user_secret" in result and "USER_KEY" in result
        assert "user_password: !user_secret" in result
        assert "key: !user_secret" in result and "providers" in result and "list" in result
        
        # Load the result to verify structure
        processed_yaml = load_yaml_with_secrets(result)
        
        # Verify structure is preserved
        assert "server" in processed_yaml
        assert "bedrock" in processed_yaml["server"]
        assert "database" in processed_yaml
        assert "providers" in processed_yaml
        assert "list" in processed_yaml["providers"]
        assert len(processed_yaml["providers"]["list"]) == 2


@pytest.mark.asyncio
async def test_empty_quotes_post_processing(mock_secrets_client):
    """Test post-processing to remove empty quotes from secret tags."""
    yaml_content = """
server:
  # Empty developer secret (would be prompted for)
  api_key: !developer_secret
  # Empty user secret
  user_key: !user_secret
"""
    
    # Override create_secret to return a deterministic handle
    async def mock_create_secret(name, secret_type, value):
        return "mock-handle"
    
    # Replace the mock's create_secret with our version
    mock_secrets_client.create_secret = mock_create_secret
    
    # Process with mocked prompt values (simulates interactive input)
    with patch("typer.prompt", return_value="prompted-value"):
        result = await processor_module.process_secrets_in_config(yaml_content, mock_secrets_client)
    
    # Verify no empty quotes remain for user secrets
    assert "user_key: !user_secret" in result
    assert "user_key: !user_secret \"\"" not in result
    assert "user_key: !user_secret ''" not in result


# REAL WORLD EXAMPLES FROM CLAUDE.md

@pytest.mark.asyncio
async def test_deploy_phase_example_from_design(mock_secrets_client, monkeypatch):
    """Test a real-world example from the design document in CLAUDE.md."""
    # Set environment variables as they would be in the example
    monkeypatch.setenv("BEDROCK_KEY", "dev-bedrock-key-from-env")
    
    # From the CLAUDE.md example
    yaml_content = """
# $schema: ...
server:
  bedrock:
    # Value comes from env var BEDROCK_KEY
    api_key: !developer_secret BEDROCK_KEY
    # Value collected during configure, env var USER_KEY is an override
    user_access_key: !user_secret USER_KEY
database:
  # Must be prompted for during deploy if non-interactive is false
  password: !developer_secret
"""
    
    # Mock prompt to simulate interactive input for database password
    with patch("typer.prompt", return_value="prompted-db-password"):
        # Process with environment variables and prompted values
        result = await processor_module.process_secrets_in_config(yaml_content, mock_secrets_client, no_prompt=False)
    
    # Expected transformations:
    # 1. BEDROCK_KEY -> resolved to env var value -> UUID handle
    # 2. database.password -> prompted for value -> UUID handle
    # 3. user_access_key -> remains as !user_secret tag
    
    # Verify developer secrets were transformed to handles
    assert "12345678-abcd-1234-efgh-dev-server-bedrock-api_key" in result
    assert "12345678-abcd-1234-efgh-dev-database-password" in result
    
    # Verify user secret remained as a tag
    assert "user_access_key: !user_secret" in result and "USER_KEY" in result
    
    # Verify API calls had correct values
    assert mock_secrets_client.create_secret.call_count == 2
    
    # Find the right calls from the arguments
    bedrock_api_key_call = None
    database_password_call = None
    
    for call in mock_secrets_client.create_secret.call_args_list:
        _, kwargs = call
        if kwargs["name"] == "server.bedrock.api_key":
            bedrock_api_key_call = kwargs
        elif kwargs["name"] == "database.password":
            database_password_call = kwargs
    
    # Should use the env var value
    assert bedrock_api_key_call is not None
    assert bedrock_api_key_call["value"] == "dev-bedrock-key-from-env"
    
    # Should use the prompted value
    assert database_password_call is not None
    assert database_password_call["value"] == "prompted-db-password"