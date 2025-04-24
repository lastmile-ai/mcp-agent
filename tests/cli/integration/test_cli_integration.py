"""Integration tests for the MCP Agent CLI deploy command.

These tests verify that the CLI can correctly process configuration files with secrets
and interact with the Secrets API to transform them properly.

Prerequisites:
1. Web app running: `cd www && pnpm run dev` or `cd www && pnpm run webdev`
2. Valid API token in the TEST_API_TOKEN environment variable

Run with: pytest -m integration
"""

import os
import json
import yaml
import tempfile
import subprocess
import uuid
from pathlib import Path
import pytest

from tests.fixtures.api_test_utils import setup_api_for_testing, APIMode

# Mark all tests in this module with the integration marker
pytestmark = pytest.mark.integration

# Fixture to get API credentials when needed
@pytest.fixture(scope="module")
def api_credentials():
    """Get API credentials from the test manager."""
    return setup_api_for_testing(APIMode.AUTO)


def test_cli_deploy_with_secrets(api_credentials):
    """Test the CLI deploy command with a configuration file containing secrets."""
    API_URL, API_TOKEN = api_credentials
    # Create a temporary config file with secrets
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w+', delete=False) as temp:
        # Generate a unique test name
        test_name = f"test-cli-{uuid.uuid4().hex[:8]}"
        
        # Create a test config with a developer secret and a user secret
        config = {
            "name": test_name,
            "api": {
                "key": "!developer_secret test-api-key"  # A simple developer secret
            },
            "database": {
                "password": "!user_secret"  # A user secret placeholder
            }
        }
        
        # Write the config to the temp file
        yaml.dump(config, temp)
        temp_path = temp.name
    
    try:
        # Create a temp file for the transformed output
        output_path = f"{temp_path}.transformed.yaml"
        
        # Run the CLI deploy command
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            temp_path,
            "--output-file", output_path,
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"  # Don't actually deploy
        ]
        
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"
        
        # Check for expected success messages in output
        assert "Secrets processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout
        
        # Verify the transformed file exists
        assert os.path.exists(output_path), "Transformed file was not created"
        
        # Read the transformed config
        with open(output_path, 'r') as f:
            transformed_config = yaml.safe_load(f)
        
        # Verify the structure is preserved
        assert transformed_config["name"] == test_name
        
        # Verify the developer secret was transformed to a handle
        assert transformed_config["api"]["key"].startswith("mcpac_dev_")
        
        # Verify the user secret was transformed to a handle
        assert transformed_config["database"]["password"].startswith("mcpac_usr_")
        
    finally:
        # Clean up temp files
        for path in [temp_path, output_path]:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except:
                pass


def test_cli_deploy_with_env_var_secret(api_credentials):
    """Test the CLI deploy command with a secret from an environment variable."""
    API_URL, API_TOKEN = api_credentials
    # Set a test environment variable
    env_var_name = f"MCP_TEST_SECRET_{uuid.uuid4().hex[:8]}".upper()
    secret_value = f"secret-value-{uuid.uuid4().hex[:8]}"
    os.environ[env_var_name] = secret_value
    
    # Create a temporary config file with an environment variable reference
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w+', delete=False) as temp:
        # Create a test config with a developer secret from env var
        config = {
            "api": {
                "key": f"!developer_secret ${{oc.env:{env_var_name}}}"
            }
        }
        
        # Write the config to the temp file
        yaml.dump(config, temp)
        temp_path = temp.name
    
    try:
        # Create a temp file for the transformed output
        output_path = f"{temp_path}.transformed.yaml"
        
        # Run the CLI deploy command
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            temp_path,
            "--output-file", output_path,
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"  # Don't actually deploy
        ]
        
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"
        
        # Check for expected success messages in output
        assert "Resolved environment variable" in result.stdout
        assert "Secrets processed successfully" in result.stdout
        
        # Verify the transformed file exists
        assert os.path.exists(output_path), "Transformed file was not created"
        
        # Read the transformed config
        with open(output_path, 'r') as f:
            transformed_config = yaml.safe_load(f)
        
        # Verify the environment variable secret was transformed to a handle
        assert transformed_config["api"]["key"].startswith("mcpac_dev_")
        
    finally:
        # Clean up temp files
        for path in [temp_path, output_path]:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except:
                pass
            
        # Remove test environment variable
        if env_var_name in os.environ:
            del os.environ[env_var_name]


def test_cli_error_handling(api_credentials):
    """Test the CLI error handling for invalid configs or missing credentials."""
    API_URL, API_TOKEN = api_credentials
    # Test with missing API token
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w+', delete=False) as temp:
        yaml.dump({"test": "data"}, temp)
        temp_path = temp.name
    
    try:
        # Run without an API token
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            temp_path,
            "--api-url", API_URL,
            "--api-token", "",  # Empty token
            "--dry-run"
        ]
        
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Verify the command failed
        assert result.returncode != 0
        
        # Check for expected error message
        assert "MCP_SECRETS_API_TOKEN environment variable or --api-token option must be set" in result.stderr
        
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass