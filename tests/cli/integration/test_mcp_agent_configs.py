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
import uuid

import pytest
import yaml
from typer.testing import CliRunner

from mcp_agent_cloud.secrets.yaml_tags import (
    SecretYamlLoader, UserSecret, DeveloperSecret,
    load_yaml_with_secrets
)

from mcp_agent_cloud.cli.main import app
from mcp_agent_cloud.secrets.constants import SecretType
from mcp_agent_cloud.secrets.api_client import SecretsClient
from tests.fixtures.api_test_utils import setup_api_for_testing, APIMode


# These tests will be marked with the integration marker
pytestmark = pytest.mark.integration


# Directory containing our realistic fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "realistic_mcp_configs"

# List of fixture scenarios to test
FIXTURE_SCENARIOS = [
    "basic_agent",
    "advanced_agent",
    "complex_integrations"
]


@pytest.fixture
def setup_env_vars():
    """Set up environment variables for the test."""
    # Save original environment variables
    orig_env = os.environ.copy()
    
    # Set test environment variables for all possible secrets
    os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-api-key"
    os.environ["GOOGLE_API_KEY"] = "test-google-api-key"
    os.environ["AWS_ACCESS_KEY_ID"] = "test-aws-access-key-id"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-aws-secret-access-key"
    os.environ["DB_USER"] = "test-db-user"
    os.environ["DB_PASSWORD"] = "test-db-password"
    os.environ["VECTOR_DB_API_KEY"] = "test-vector-db-api-key"
    os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-slack-bot-token"
    os.environ["SLACK_TEAM_ID"] = "T12345678"
    os.environ["GITHUB_PAT"] = "github_pat_test_token"
    os.environ["ZENDESK_API_KEY"] = "test-zendesk-api-key"
    os.environ["ZENDESK_SUBDOMAIN"] = "test-company"
    os.environ["ZENDESK_EMAIL"] = "test@example.com"
    
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
    return SecretsClient(api_url=api_url, api_key=api_token)


class TestMcpAgentConfigIntegration:
    """Test processing of MCP Agent configurations with realistic fixtures."""
    
    @pytest.mark.parametrize("scenario", FIXTURE_SCENARIOS)
    def test_config_cli_deploy(self, setup_env_vars, api_credentials, scenario):
        """Test processing a configuration via CLI for each realistic scenario."""
        # Get API credentials from fixture
        api_url, api_token = api_credentials
        
        # Get paths for this scenario
        config_path = FIXTURES_DIR / scenario / "mcp_agent.config.yaml"
        secrets_path = FIXTURES_DIR / scenario / "mcp_agent.secrets.yaml"
        
        # Ensure the fixture files exist
        assert config_path.exists(), f"Config fixture {config_path} does not exist"
        assert secrets_path.exists(), f"Secrets fixture {secrets_path} does not exist"
        
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
                    "--api-key", api_token,
                    "--secrets-file", str(secrets_path),
                    "--secrets-output-file", output_path,
                    "--dry-run",
                    str(config_path)
                ]
            )
            
            # Check that the command succeeded
            assert result.exit_code == 0, f"Error: {result.stdout}"
            assert "Secrets file processed successfully" in result.stdout
            
            # Check that the output file exists and was transformed properly
            assert Path(output_path).exists()
            
            # Load the transformed config
            with open(output_path, "r") as f:
                transformed = yaml.safe_load(f)
            
            # Helper function to check if a string is a valid UUID
            def is_valid_uuid(val):
                try:
                    uuid.UUID(val)
                    return True
                except (ValueError, TypeError):
                    return False
            
            # Helper function to recursively check all keys in a config
            def check_secrets_recursive(config, parent_path=""):
                if isinstance(config, dict):
                    for key, value in config.items():
                        current_path = f"{parent_path}.{key}" if parent_path else key
                        if isinstance(value, (dict, list)):
                            check_secrets_recursive(value, current_path)
                        elif isinstance(value, str) and "!developer_secret" in value:
                            assert False, f"Found unprocessed developer secret at {current_path}: {value}"
                        elif isinstance(value, str) and "secret" not in key.lower():
                            # For non-secret string values, they should remain unchanged
                            pass
                        elif isinstance(value, str) and is_valid_uuid(value):
                            # For UUIDs, these are probably transformed secrets
                            print(f"Found UUID at {current_path}: {value}")
                        elif isinstance(value, str) and "!user_secret" in value:
                            assert False, f"Found unprocessed user secret at {current_path}: {value}"
                elif isinstance(config, list):
                    for i, item in enumerate(config):
                        check_secrets_recursive(item, f"{parent_path}[{i}]")
            
            # Check the transformed output recursively
            check_secrets_recursive(transformed)
            
            # Load the original secrets file to check what was supposed to be transformed
            with open(secrets_path, "r") as f:
                original_content = f.read()
            
            # Count how many developer secrets we expect to be transformed
            expected_dev_secrets = original_content.count("!developer_secret")
            expected_user_secrets = original_content.count("!user_secret")
            
            # Confirm the user saw information about transformations
            assert f"Transformed {expected_dev_secrets} developer secret(s)" in result.stdout
            if expected_user_secrets > 0:
                assert f"Retained {expected_user_secrets} user secret(s)" in result.stdout
                
        finally:
            # Clean up the output file
            if Path(output_path).exists():
                Path(output_path).unlink()
    
    @pytest.mark.asyncio
    async def test_complex_config_direct_api(self, setup_env_vars, api_client):
        """Test processing a complex configuration directly with the API client."""
        # Get path for the complex integration scenario
        scenario = "complex_integrations"
        secrets_path = FIXTURES_DIR / scenario / "mcp_agent.secrets.yaml"
        
        # Ensure the fixture files exist
        assert secrets_path.exists(), f"Secrets fixture {secrets_path} does not exist"
        
        # Load the original secrets file with custom YAML loader for secret tags
        with open(secrets_path, "r") as f:
            config_str = f.read()
        config = load_yaml_with_secrets(config_str)
        
        # List to store created secret IDs for cleanup
        created_secrets = []
        
        try:
            # Helper function to recursively process secrets
            async def process_secrets_recursive(config, path=""):
                if isinstance(config, dict):
                    for key, value in config.items():
                        current_path = f"{path}.{key}" if path else key
                        # Process nested structures recursively
                        if isinstance(value, (dict, list)):
                            await process_secrets_recursive(value, current_path)
                        # Process developer secrets using the API
                        elif isinstance(value, DeveloperSecret):
                            # Get the value - might be env var reference
                            env_var = value.value
                            secret_value = env_var
                            
                            if env_var and env_var.startswith("${oc.env:") and env_var.endswith("}"):
                                # Extract env var name
                                env_name = env_var[9:-1]
                                secret_value = os.environ.get(env_name, "")
                                
                            # Create secret via API
                            secret_id = await api_client.create_secret(
                                name=current_path,
                                secret_type=SecretType.DEVELOPER,
                                value=secret_value or "test-value-for-empty-developer-secret"
                            )
                            created_secrets.append(secret_id)
                            
                            # Verify we can retrieve the secret
                            retrieved_value = await api_client.get_secret_value(secret_id)
                            assert retrieved_value == (secret_value or "test-value-for-empty-developer-secret"), \
                                f"Retrieved value {retrieved_value} does not match expected {secret_value}"
                                
                        # Process user secrets using the API
                        elif isinstance(value, UserSecret):
                            # Create user secret (placeholder)
                            secret_id = await api_client.create_secret(
                                name=current_path,
                                secret_type=SecretType.USER,
                                value="initial-value-required"  # API requires a value
                            )
                            created_secrets.append(secret_id)
                            
                            # Set a value for testing
                            test_value = f"user-provided-value-for-{current_path}"
                            await api_client.set_secret_value(secret_id, test_value)
                            
                            # Verify we can retrieve the secret
                            retrieved_value = await api_client.get_secret_value(secret_id)
                            assert retrieved_value == test_value, f"Retrieved value {retrieved_value} does not match expected {test_value}"
                elif isinstance(config, list):
                    for i, item in enumerate(config):
                        await process_secrets_recursive(item, f"{path}[{i}]")
            
            # Process secrets recursively
            await process_secrets_recursive(config)
            
            # List secrets to verify they were created
            secrets_list = await api_client.list_secrets()
            assert len(secrets_list) >= len(created_secrets), "Not all secrets were listed"
            
        finally:
            # Clean up created secrets
            for secret_id in created_secrets:
                try:
                    deleted_id = await api_client.delete_secret(secret_id)
                    assert deleted_id == secret_id, f"Deleted secret ID {deleted_id} doesn't match original {secret_id}"
                except Exception as e:
                    print(f"Error cleaning up secret {secret_id}: {str(e)}")