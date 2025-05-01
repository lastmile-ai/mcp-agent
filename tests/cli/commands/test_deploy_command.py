"""Tests for the deploy command functionality in the CLI."""

import os
import tempfile
from pathlib import Path
import pytest
import yaml
import typer
from unittest.mock import patch, MagicMock, AsyncMock

from typer.testing import CliRunner

from mcp_agent_cloud.cli.main import app
from mcp_agent_cloud.core.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


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
def temp_config_dir():
    """Create a temporary directory with sample config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write sample config file
        config_content = """
server:
  host: localhost
  port: 8000
database:
  username: admin
"""
        config_path = Path(temp_dir) / "mcp-agent.config.yaml"
        with open(config_path, "w") as f:
            f.write(config_content)
        
        # Write sample secrets file - only include secrets with env vars
        secrets_content = """
server:
  api_key: !developer_secret SERVER_API_KEY
database:
  # password: !developer_secret  # Removed this as it would cause prompting
  user_token: !user_secret USER_TOKEN
"""
        secrets_path = Path(temp_dir) / "mcp-agent.secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write(secrets_content)
        
        yield temp_dir


def test_deploy_command_help(runner):
    """Test that the deploy command help displays expected arguments and options."""
    result = runner.invoke(app, ["deploy", "--help"])
    
    # Command should succeed
    assert result.exit_code == 0
    
    # Expected options from the updated CLAUDE.md spec
    assert "--secrets-file" in result.stdout or "-s" in result.stdout
    assert "--config-file" in result.stdout or "-c" in result.stdout
    assert "--secrets-output-file" in result.stdout or "-o" in result.stdout
    assert "--api-url" in result.stdout
    assert "--api-key" in result.stdout
    assert "--non-interactive" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--no-secrets" in result.stdout


def test_deploy_command_basic(runner, temp_config_dir, mock_secrets_client):
    """Test the basic deploy command with mocked secrets client."""
    # Set up paths
    config_path = Path(temp_config_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(temp_config_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(temp_config_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Mock the environment variables
    with patch.dict(os.environ, {"SERVER_API_KEY": "test-server-key", "MCP_API_KEY": "test-api-key"}):
        # Mock the process_config_secrets function to return a dummy value
        async def mock_process_secrets(*args, **kwargs):
            # Write a dummy transformed file
            with open(kwargs.get('output_path', output_path), 'w') as f:
                f.write("# Transformed file\ntest: value\n")
            return {"developer_secrets": [], "user_secrets": []}
        
        with patch("mcp_agent_cloud.secrets.processor.process_config_secrets", side_effect=mock_process_secrets):
            # Run the deploy command
            result = runner.invoke(
                app, 
                [
                    "deploy", 
                    "--secrets-file", str(secrets_path),
                    "--config-file", str(config_path),
                    "--secrets-output-file", str(output_path),
                    "--api-url", "http://test-api.com",
                    "--api-key", "test-api-key",
                    "--dry-run",  # Use dry run to avoid actual deployment
                    "--non-interactive"  # Prevent prompting for input
                ]
            )
    
    # Check command exit code
    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"
    
    # Verify the command was successful
    assert "Secrets file processed successfully" in result.stdout
    
    # Check for expected output file path and dry run mode
    assert "Transformed secrets file written to" in result.stdout
    assert "dry run" in result.stdout.lower()


def test_deploy_command_no_secrets(runner, temp_config_dir):
    """Test deploy command with --no-secrets flag."""
    # Set up paths
    config_path = Path(temp_config_dir) / "mcp-agent.config.yaml"
    secrets_path = Path(temp_config_dir) / "mcp-agent.secrets.yaml"
    output_path = Path(temp_config_dir) / "mcp-agent.deployed.secrets.yaml"
    
    # Run with --no-secrets flag and --dry-run to avoid real deployment
    with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
        # Mock the wrangler deployment
        mock_deploy.return_value = None
        
        result = runner.invoke(
            app,
            [
                "deploy",
                "--secrets-file", str(secrets_path),
                "--config-file", str(config_path),
                "--secrets-output-file", str(output_path),
                "--no-secrets",
                "--dry-run"  # Add dry-run mode
            ]
        )
    
    # Command should succeed
    assert result.exit_code == 0
    
    # Check output mentions skipping secrets
    assert "skipping secrets processing" in result.stdout.lower()
    

def test_deploy_with_separate_secrets_file():
    """Test the deploy command with a separate secrets file."""
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a config file
        config_content = """
server:
  host: example.com
  port: 443
"""
        config_path = temp_path / "config.yaml"
        with open(config_path, "w") as f:
            f.write(config_content)
        
        # Create a secrets file with developer and user secrets
        secrets_content = """
server:
  api_key: !developer_secret API_KEY
  user_token: !user_secret USER_TOKEN
"""
        secrets_path = temp_path / "secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write(secrets_content)
        
        # Create output path
        secrets_output = temp_path / "deployed.secrets.yaml"
        
        # Call deploy_config with wrangler_deploy mocked
        with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
            # Mock wrangler_deploy to prevent actual deployment
            mock_deploy.return_value = None
            
            # Set a test env var
            with patch.dict(os.environ, {"API_KEY": "test-key"}):
                # Use the real deploy_config function
                from mcp_agent_cloud.commands.deploy import deploy_config
                
                # Run the deploy command
                result = deploy_config(
                    config_file=config_path,
                    secrets_file=secrets_path,
                    secrets_output_file=secrets_output,
                    no_secrets=False,
                    api_url="http://test.api/",
                    api_key="test-token",
                    dry_run=True,
                    non_interactive=True  # Set to True to avoid prompting
                )
            
            # Verify deploy was successful
            assert os.path.exists(secrets_output), "Output file should exist"
            
            # Verify the function returned the expected output path
            assert result == str(config_path)  # deploy_config returns config path


def test_deploy_with_missing_env_vars():
    """Test deploy with missing environment variables and non-interactive mode."""
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a config file
        config_path = temp_path / "config.yaml"
        with open(config_path, "w") as f:
            f.write("server:\n  host: example.com\n")
        
        # Create a secrets file with developer secret that needs prompting
        secrets_path = temp_path / "secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write("server:\n  api_key: !developer_secret MISSING_ENV_VAR\n")
        
        # Create output path
        secrets_output = temp_path / "deployed.secrets.yaml"
        
        # Call the deploy_config function directly with missing env var
        from mcp_agent_cloud.commands.deploy import deploy_config
        
        # Call with non_interactive=True, which should fail with typer.Exit
        with pytest.raises(typer.Exit):
            deploy_config(
                config_file=config_path,
                secrets_file=secrets_path,
                secrets_output_file=secrets_output,
                no_secrets=False,
                api_url="http://test.api/",
                api_key="test-token",
                dry_run=True,
                non_interactive=True  # This should cause failure with missing env var
            )


def test_deploy_with_mock_client():
    """Test deploy using MockSecretsClient with --dry-run flag."""
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create minimal config and secrets files
        config_path = temp_path / "config.yaml"
        with open(config_path, "w") as f:
            f.write("server:\n  host: example.com\n")
        
        secrets_path = temp_path / "secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write("server:\n  api_key: !developer_secret TEST_KEY\n")
        
        # Create output path
        secrets_output = temp_path / "deployed.secrets.yaml"
        
        # Mock environment variables
        with patch.dict(os.environ, {"TEST_KEY": "test-value"}):
            # Mock the wrangler deployment
            with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy") as mock_deploy:
                # Prevent actual deployment
                mock_deploy.return_value = None
                
                # Call the command directly
                from mcp_agent_cloud.commands.deploy import deploy_config
                
                result = deploy_config(
                    secrets_file=secrets_path,
                    config_file=config_path,
                    secrets_output_file=str(secrets_output),
                    api_url="http://test.api/",
                    api_key="test-token",
                    dry_run=True,
                    non_interactive=False,
                    no_secrets=False
                )
                
                # Verify the deploy was successful and returned the config path
                assert result == str(config_path)  # deploy_config returns config path
                
                # Verify the output file exists
                assert os.path.exists(secrets_output)