"""Integration tests for processing MCP Agent configurations.

These tests require a running Vault server and should be run manually.
They are marked with 'vault_integration' so they can be skipped by default.

To run these tests:
    1. Start a Vault server (e.g., using docker-compose)
    2. Set the VAULT_ADDR and VAULT_TOKEN environment variables
    3. Run pytest with the vault_integration mark:
       pytest -m vault_integration
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mcp_agent_cloud.cli.main import app
from mcp_agent_cloud.secrets.constants import SecretsMode
from mcp_agent_cloud.secrets.factory import get_secrets_client


# These tests will be marked with the vault_integration marker
pytestmark = [
    pytest.mark.vault_integration
]


@pytest.fixture
def setup_env_vars():
    """Set up environment variables for the test."""
    # Save original environment variables
    orig_env = os.environ.copy()
    
    # Set test environment variables
    os.environ["AWS_REGION"] = "us-west-2"
    os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key-id"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-access-key"
    os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-api-key"
    
    yield
    
    # Restore original environment variables
    os.environ.clear()
    os.environ.update(orig_env)


class TestMcpAgentConfigIntegration:
    """Test processing of MCP Agent configurations."""
    
    def test_bedrock_config_cli(self, setup_env_vars, vault_instance):
        """Test processing a Bedrock configuration via CLI."""
        # Get Vault credentials from fixture
        vault_addr, vault_token = vault_instance
        
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as output_file:
            output_path = output_file.name
        
        try:
            # Run the CLI command with command-line options
            result = runner.invoke(
                app, 
                [
                    "deploy", 
                    "--secrets-mode", "direct_vault",
                    "--vault-addr", vault_addr,
                    "--vault-token", vault_token,
                    "--dry-run",
                    "-o", output_path,
                    str(Path(__file__).parent.parent / "fixtures" / "bedrock_config.yaml")
                ],
                env={
                    "AWS_REGION": "us-west-2",
                    "AWS_ACCESS_KEY_ID": "test-access-key-id",
                    "AWS_SECRET_ACCESS_KEY": "test-secret-access-key",
                    "OPENAI_API_KEY": "test-openai-api-key",
                    "ANTHROPIC_API_KEY": "test-anthropic-api-key",
                }
            )
            
            # Check that the command succeeded
            assert result.exit_code == 0, f"Error: {result.stdout}"
            assert "Secrets processed successfully" in result.stdout
            
            # Check that the output file exists and was transformed properly
            assert Path(output_path).exists()
            
            # Load the transformed config
            with open(output_path, "r") as f:
                config = yaml.safe_load(f)
            
            # Check that secrets were replaced with handles
            assert isinstance(config["server"]["bedrock"]["api_key"], str)
            assert config["server"]["bedrock"]["api_key"].startswith("mcpac_mvp0_dev_")
            assert isinstance(config["server"]["bedrock"]["user_access_key"], str)
            assert config["server"]["bedrock"]["user_access_key"].startswith("mcpac_mvp0_usr_")
            
            # Ensure non-secret values were not changed
            assert config["server"]["bedrock"]["default_model"] == "anthropic.claude-3-haiku-20240307-v1:0"
            
        finally:
            # Clean up the output file
            if Path(output_path).exists():
                Path(output_path).unlink()
    
    @pytest.mark.asyncio
    async def test_service_integration_config(self, setup_env_vars, vault_instance):
        """Test processing a complex service integration configuration."""
        # Get Vault credentials from fixture
        vault_addr, vault_token = vault_instance
        
        # Set additional environment variables for this test
        os.environ["VAULT_ADDR"] = vault_addr
        os.environ["VAULT_TOKEN"] = vault_token
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-bot-token"
        os.environ["SLACK_TEAM_ID"] = "T01234567"
        os.environ["GITHUB_PAT"] = "github_pat_test_token"
        os.environ["DB_PASSWORD"] = "test-db-password"
        
        # Get the client for direct Vault mode with explicit credentials
        client = get_secrets_client(
            SecretsMode.DIRECT_VAULT,
            vault_addr=vault_addr,
            vault_token=vault_token
        )
        
        # Load the config file
        config_path = Path(__file__).parent.parent / "fixtures" / "service_integration_config.yaml"
        with open(config_path, "r") as f:
            config_str = f.read()
        
        # Create a temporary output file
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as output_file:
            output_path = output_file.name
        
        try:
            from mcp_agent_cloud.secrets.processor import process_config_secrets
            
            # Process the config with explicit credentials
            await process_config_secrets(
                config_path=str(config_path),
                output_path=output_path,
                secrets_mode=SecretsMode.DIRECT_VAULT,
                vault_addr=vault_addr,
                vault_token=vault_token
            )
            
            # Check that the output file exists
            assert Path(output_path).exists()
            
            # Load the transformed config
            with open(output_path, "r") as f:
                transformed_str = f.read()
                config = yaml.safe_load(transformed_str)
            
            # Check that nested secrets were transformed
            assert isinstance(config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"], str)
            assert config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"].startswith("mcpac_mvp0_dev_")
            
            assert isinstance(config["mcp"]["servers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"], str)
            assert config["mcp"]["servers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"].startswith("mcpac_mvp0_dev_")
            
            assert isinstance(config["openai"]["api_key"], str)
            assert config["openai"]["api_key"].startswith("mcpac_mvp0_dev_")
            
            assert isinstance(config["openai"]["organization_id"], str)
            assert config["openai"]["organization_id"].startswith("mcpac_mvp0_usr_")
            
            # Check some of the transformed values in Vault
            slack_token_handle = config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"]
            slack_token_value = await client.get_secret_value(slack_token_handle)
            assert slack_token_value == "xoxb-test-bot-token"
            
            # Confirm user secrets don't have values yet
            with pytest.raises(ValueError):
                await client.get_secret_value(config["openai"]["organization_id"])
            
            # Set a value for a user secret
            await client.set_secret_value(config["openai"]["organization_id"], "org-123456")
            
            # Verify it was set correctly
            org_id_value = await client.get_secret_value(config["openai"]["organization_id"])
            assert org_id_value == "org-123456"
            
        finally:
            # Clean up the output file
            if Path(output_path).exists():
                Path(output_path).unlink()