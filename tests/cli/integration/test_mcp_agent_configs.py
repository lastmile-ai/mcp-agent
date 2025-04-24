"""Integration tests for processing MCP Agent configurations.

These tests require a running web app and Vault instance.
They are marked with 'integration' so they can be skipped by default.

To run these tests:
    1. Start the web app: pnpm run webdev
    2. Run pytest with the integration mark:
       pytest -m integration
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mcp_agent_cloud.cli.main import app
from mcp_agent_cloud.secrets.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient
from tests.fixtures.api_test_utils import setup_api_for_testing, APIMode


# These tests will be marked with the integration marker
pytestmark = pytest.mark.integration


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


@pytest.fixture
def api_credentials():
    """Get API credentials using the API test manager."""
    # Use the API test manager to set up the API
    api_url, api_token = setup_api_for_testing(APIMode.AUTO)
    return api_url, api_token


@pytest.fixture
def api_client(api_credentials):
    """Create a SecretsClient."""
    api_url, api_token = api_credentials
    return SecretsClient(api_url=api_url, api_token=api_token)


class TestMcpAgentConfigIntegration:
    """Test processing of MCP Agent configurations."""
    
    def test_bedrock_config_cli(self, setup_env_vars, api_credentials):
        """Test processing a Bedrock configuration via CLI."""
        # Get API credentials from fixture
        api_url, api_token = api_credentials
        
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as output_file:
            output_path = output_file.name
        
        try:
            # Run the CLI command with command-line options
            result = runner.invoke(
                app, 
                [
                    "deploy", 
                    "--api-url", api_url,
                    "--api-token", api_token,
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
            assert config["server"]["bedrock"]["api_key"].startswith("mcpac_dev_")
            assert isinstance(config["server"]["bedrock"]["user_access_key"], str)
            assert config["server"]["bedrock"]["user_access_key"].startswith("mcpac_usr_")
            
            # Ensure non-secret values were not changed
            assert config["server"]["bedrock"]["default_model"] == "anthropic.claude-3-haiku-20240307-v1:0"
            
        finally:
            # Clean up the output file
            if Path(output_path).exists():
                Path(output_path).unlink()
    
    @pytest.mark.asyncio
    async def test_service_integration_config(self, setup_env_vars, api_client, api_credentials):
        """Test processing a complex service integration configuration."""
        # Get API credentials from fixture
        api_url, api_token = api_credentials
        
        # Set additional environment variables for this test
        os.environ["MCP_SECRETS_API_URL"] = api_url
        os.environ["MCP_SECRETS_API_TOKEN"] = api_token
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-bot-token"
        os.environ["SLACK_TEAM_ID"] = "T01234567"
        os.environ["GITHUB_PAT"] = "github_pat_test_token"
        os.environ["DB_PASSWORD"] = "test-db-password"
        
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
                api_url=api_url,
                api_token=api_token
            )
            
            # Check that the output file exists
            assert Path(output_path).exists()
            
            # Load the transformed config
            with open(output_path, "r") as f:
                transformed_str = f.read()
                config = yaml.safe_load(transformed_str)
            
            # Check that nested secrets were transformed
            assert isinstance(config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"], str)
            assert config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"].startswith("mcpac_dev_")
            
            assert isinstance(config["mcp"]["servers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"], str)
            assert config["mcp"]["servers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"].startswith("mcpac_dev_")
            
            assert isinstance(config["openai"]["api_key"], str)
            assert config["openai"]["api_key"].startswith("mcpac_dev_")
            
            assert isinstance(config["openai"]["organization_id"], str)
            assert config["openai"]["organization_id"].startswith("mcpac_usr_")
            
            # Check some of the transformed values via the API
            slack_token_handle = config["mcp"]["servers"]["slack"]["env"]["SLACK_BOT_TOKEN"]
            slack_token_value = await api_client.get_secret_value(slack_token_handle)
            assert slack_token_value == "xoxb-test-bot-token"
            
            # Set a value for a user secret
            user_secret_handle = config["openai"]["organization_id"]
            await api_client.set_secret_value(user_secret_handle, "org-123456")
            
            # Verify it was set correctly
            org_id_value = await api_client.get_secret_value(user_secret_handle)
            assert org_id_value == "org-123456"
            
            # Clean up created secrets
            await api_client.delete_secret(slack_token_handle)
            await api_client.delete_secret(user_secret_handle)
            
        finally:
            # Clean up the output file
            if Path(output_path).exists():
                Path(output_path).unlink()