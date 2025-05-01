"""Integration tests for the complete deploy workflow."""

import os
import tempfile
import shutil
from pathlib import Path
import pytest
import yaml
import typer
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_agent_cloud.commands.deploy import deploy_config
from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.core.constants import SecretType


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient that returns predictable handles."""
    client = AsyncMock(spec=SecretsClient)
    
    # Configure create_secret to return deterministic handles based on secret name
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a handle based on the path and type
        prefix = "dev" if secret_type == SecretType.DEVELOPER else "usr"
        secret_id = f"test-{prefix}-{name.replace('.', '-')}"
        return secret_id
    
    client.create_secret.side_effect = mock_create_secret
    return client


@pytest.fixture
def real_world_example_dir():
    """Create a temporary directory with the real-world example from CLAUDE.md."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write sample config file based on CLAUDE.md
        config_content = """
# $schema: ...
execution_engine: asyncio
mcp:
  servers:
    bedrock_server:
      config_ref: "server.bedrock" 
# ... other non-sensitive config
"""
        config_path = Path(temp_dir) / "mcp-agent.config.yaml"
        with open(config_path, "w") as f:
            f.write(config_content)
        
        # Write sample secrets file based on CLAUDE.md
        secrets_content = """
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
        secrets_path = Path(temp_dir) / "mcp-agent.secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write(secrets_content)
        
        yield temp_dir


def test_deploy_e2e_with_env_vars(real_world_example_dir, mock_secrets_client):
    """Test end-to-end deploy workflow with environment variables."""
    # Set up paths
    config_path = Path(real_world_example_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(real_world_example_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(real_world_example_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Set test environment variables
    with patch.dict(os.environ, {
        "BEDROCK_KEY": "dev-bedrock-key-from-env",
        "MCP_API_BASE_URL": "https://api.example.com",
        "MCP_API_KEY": "your-api-key-here"
    }):
        # Create a mock for wrangler_deploy to avoid actual deployment
        with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
            # Simulate database password prompt
            with patch("typer.prompt", return_value="prompted-db-password"):
                # Execute deploy_config with dry_run=True
                result = deploy_config(
                    config_file=config_path,
                    secrets_file=secrets_path,
                    secrets_output_file=output_path,
                    no_secrets=False,
                    api_url="https://api.example.com",
                    api_key="your-api-key-here",
                    dry_run=True,
                    non_interactive=False
                )
    
    # Verify the output file exists
    assert output_path.exists()
    
    # Verify the content of the output file
    with open(output_path, "r") as f:
        content = f.read()
    
    # Check key aspects of the output
    assert "api_key:" in content
    assert "password:" in content
    # Check for user_access_key with USER_KEY - may have quotes around it
    assert any(pattern in content for pattern in [
        "user_access_key: !user_secret USER_KEY",
        "user_access_key: !user_secret 'USER_KEY'"
    ])


def test_deploy_e2e_with_no_secrets(real_world_example_dir):
    """Test end-to-end deploy workflow with --no-secrets flag."""
    # Set up paths
    config_path = Path(real_world_example_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(real_world_example_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(real_world_example_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Create a mock for wrangler_deploy to avoid actual deployment
    with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
        # Run with no_secrets=True
        result = deploy_config(
            config_file=config_path,
            secrets_file=secrets_path,
            secrets_output_file=output_path,
            no_secrets=True,  # Skip secrets processing
            api_url=None,
            api_key=None,
            dry_run=True,
            non_interactive=False
        )
    
    # Verify the result is the config path
    assert result == str(config_path)


def test_deploy_e2e_with_non_interactive(real_world_example_dir):
    """Test end-to-end deploy workflow with --non-interactive flag."""
    # Set up paths
    config_path = Path(real_world_example_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(real_world_example_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(real_world_example_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Set only one of the required env vars
    with patch.dict(os.environ, {
        "BEDROCK_KEY": "dev-bedrock-key-from-env",
        "MCP_API_BASE_URL": "https://api.example.com",
        "MCP_API_KEY": "your-api-key-here"
    }):
        # Run with non_interactive=True - should fail with typer.Exit
        with pytest.raises(typer.Exit):
            deploy_config(
                config_file=config_path,
                secrets_file=secrets_path,
                secrets_output_file=output_path,
                no_secrets=False,
                api_url="https://api.example.com",
                api_key="your-api-key-here",
                dry_run=True,
                non_interactive=True  # Don't prompt, fail instead
            )


def test_deploy_e2e_with_dry_run(real_world_example_dir):
    """Test end-to-end deploy workflow with --dry-run flag."""
    # Set up paths
    config_path = Path(real_world_example_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(real_world_example_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(real_world_example_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Set test environment variables and mock prompting
    with patch.dict(os.environ, {
        "BEDROCK_KEY": "dev-bedrock-key-from-env"
    }):
        # Mock typer.prompt for the database password
        with patch("typer.prompt", return_value="prompted-db-password"):
            # Mock wrangler_deploy to avoid actual deployment
            with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
                # Run with dry_run=True
                result = deploy_config(
                    config_file=config_path,
                    secrets_file=secrets_path,
                    secrets_output_file=output_path,
                    no_secrets=False,
                    api_url=None,  # Should use mock client even without API creds
                    api_key=None,
                    dry_run=True,  # Use mock client
                    non_interactive=False
                )
    
    # Verify the result is the config path
    assert result == str(config_path)
    
    # Verify the output file exists
    assert output_path.exists()
    
    # Verify the content structure (not exact values since real MockSecretsClient is used)
    with open(output_path, "r") as f:
        content = f.read()
    
    # In dry-run mode, the MockSecretsClient should create deterministic UUIDs
    assert "api_key:" in content
    assert "password:" in content
    # Check for user_access_key with USER_KEY - may have quotes around it
    assert any(pattern in content for pattern in [
        "user_access_key: !user_secret USER_KEY",
        "user_access_key: !user_secret 'USER_KEY'"
    ])