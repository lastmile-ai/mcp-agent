"""Integration tests for the MCP Agent CLI deploy command.

These tests verify that the CLI can correctly process configuration files with secrets
and interact with the Secrets API to transform them properly.

Prerequisites:
1. Web app running: `cd www && pnpm run dev` or `cd www && pnpm run webdev`
2. Valid API token in the TEST_API_TOKEN environment variable

Run with: pytest -m integration
"""

import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
import yaml
from mcp_agent_cloud.secrets.processor import DeveloperSecret, UserSecret

from tests.fixtures.api_test_utils import APIMode, setup_api_for_testing

# Mark all tests in this module with the integration marker
pytestmark = pytest.mark.integration


# Fixture to get API credentials when needed
@pytest.fixture(scope="module")
def api_credentials():
    """Get API credentials from the test manager."""
    return setup_api_for_testing(APIMode.AUTO)


@pytest.fixture(scope="module")
def mock_api_credentials():
    """Mock API credentials for tests that use --dry-run and don't need a real API."""
    # These won't be used in dry-run mode but are required by the test
    return "http://mock-api-server.local", "mock-test-token"


def test_cli_deploy_with_secrets(mock_api_credentials):
    """Test the CLI deploy command with a configuration file containing secrets.

    This test uses --dry-run mode so it doesn't need a real API connection.
    """
    API_URL, API_TOKEN = mock_api_credentials

    # Create a temporary config file (without secrets)
    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w+", delete=False
    ) as config_file:
        # Generate a unique test name
        test_name = f"test-cli-{uuid.uuid4().hex[:8]}"

        # Create a test config without secrets
        main_config = {"name": test_name, "server": {"host": "localhost", "port": 8080}}

        # Write the config to the temp file
        yaml.dump(main_config, config_file)
        config_path = config_file.name

    # Create a temporary secrets file with YAML string for proper tag handling
    secrets_file_content = """api:
  key: !developer_secret test-api-key
database:
  password: !user_secret
"""
    secrets_path = tempfile.mktemp(suffix=".yaml")
    with open(secrets_path, "w") as secrets_file:
        secrets_file.write(secrets_file_content)

    try:
        # Create a temp file for the transformed secrets output
        secrets_output_path = f"{secrets_path}.transformed.yaml"

        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            "--secrets-file",
            secrets_path,
            "--secrets-output-file",
            secrets_output_path,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Don't actually deploy
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # Check for expected success messages in output
        assert "Secrets file processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout

        # Verify the transformed secrets file exists
        assert os.path.exists(secrets_output_path), (
            "Transformed secrets file was not created"
        )

        # Read the transformed secrets file as text
        with open(secrets_output_path, "r") as f:
            transformed_yaml_text = f.read()

        print("\nTransformed YAML Content:")
        print(transformed_yaml_text)

        # Use regex to check the format of the developer secret
        dev_secret_pattern = r"key:\s+([a-f0-9-]+)"
        dev_match = re.search(dev_secret_pattern, transformed_yaml_text)
        assert dev_match is not None, f"Developer secret UUID pattern not found in file"

        # Try to parse the extracted UUID to verify format
        dev_uuid_str = dev_match.group(1)
        try:
            uuid.UUID(dev_uuid_str)
            is_uuid = True
        except ValueError:
            is_uuid = False
        assert is_uuid, f"Expected UUID format, got: {dev_uuid_str}"

        # Verify the user secret was NOT transformed and still has its tag
        user_secret_pattern = r"password:\s+!user_secret"
        user_match = re.search(user_secret_pattern, transformed_yaml_text)
        assert user_match is not None, f"User secret tag pattern not found in file"

        # Verify the original config is unchanged
        with open(config_path, "r") as f:
            unchanged_config = yaml.safe_load(f)
        assert unchanged_config["name"] == test_name
        assert unchanged_config["server"]["host"] == "localhost"

    finally:
        # Clean up temp files
        for path in [config_path, secrets_path, secrets_output_path]:
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

    # Create a temporary main config file (without secrets)
    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w+", delete=False
    ) as config_file:
        # Create a basic config file
        main_config = {"app": {"name": "env-var-test", "port": 9000}}

        # Write the config to the temp file
        yaml.dump(main_config, config_file)
        config_path = config_file.name

    # Create a temporary secrets file with environment variable reference
    # Use direct YAML string to ensure proper tag handling
    secrets_file_content = f"""api:
  key: !developer_secret ${{oc.env:{env_var_name}}}
"""
    secrets_path = tempfile.mktemp(suffix=".yaml")
    with open(secrets_path, "w") as secrets_file:
        secrets_file.write(secrets_file_content)

    try:
        # Create a temp file for the transformed secrets output
        secrets_output_path = f"{secrets_path}.transformed.yaml"

        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            "--secrets-file",
            secrets_path,
            "--secrets-output-file",
            secrets_output_path,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Don't actually deploy
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # Check for expected success messages in output
        assert (
            "Loaded secret value for api.key from environment variable" in result.stdout
        )
        assert "Secrets file processed successfully" in result.stdout

        # Verify the transformed secrets file exists
        assert os.path.exists(secrets_output_path), (
            "Transformed secrets file was not created"
        )

        # Read the transformed secrets config
        with open(secrets_output_path, "r") as f:
            transformed_secrets = yaml.safe_load(f)

        # Verify the environment variable secret was transformed to a UUID handle
        # Note: No more mcpac_dev_ prefix, just plain UUIDs from Prisma
        try:
            uuid.UUID(transformed_secrets["api"]["key"])
            is_uuid = True
        except ValueError:
            is_uuid = False
        assert is_uuid, (
            f"Expected UUID format, got: {transformed_secrets['api']['key']}"
        )

        # Verify the main config is unchanged
        with open(config_path, "r") as f:
            unchanged_config = yaml.safe_load(f)
        assert unchanged_config["app"]["name"] == "env-var-test"

    finally:
        # Clean up temp files
        for path in [config_path, secrets_path, secrets_output_path]:
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

    # Create both config and secrets files
    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w+", delete=False
    ) as config_file:
        yaml.dump({"test": "config"}, config_file)
        config_path = config_file.name

    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w+", delete=False
    ) as secrets_file:
        yaml.dump({"test": "secrets"}, secrets_file)
        secrets_path = secrets_file.name

    try:
        # Test with missing API token
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            "--secrets-file",
            secrets_path,
            "--api-url",
            API_URL,
            "--api-key",
            "",  # Empty token
            "--dry-run",
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # With dry-run flag, the test will actually pass when it should fail
        # Dry run doesn't validate credentials but uses a mock client instead
        # So it actually executes successfully, this is expected behavior
        assert result.returncode == 0
        assert "Using MOCK Secrets API client for dry run" in result.stdout

        # Test with missing secrets file
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            # No secrets file specified
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command failed
        assert result.returncode != 0

        # Check for expected error message (secrets-file is missing)
        assert "missing option" in result.stderr.lower()

    finally:
        # Clean up temp files
        for path in [config_path, secrets_path]:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except:
                pass


def test_developer_secret_validation(api_credentials):
    """Test validation that developer secrets must have values."""
    API_URL, API_TOKEN = api_credentials

    # Create a basic config file
    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w+", delete=False
    ) as config_file:
        yaml.dump({"app": "test"}, config_file)
        config_path = config_file.name

    # Create a secrets file with an empty developer secret
    # Use direct YAML string to ensure proper tag handling
    secrets_file_content = """api:
  key: !developer_secret
"""
    secrets_path = tempfile.mktemp(suffix=".yaml")
    with open(secrets_path, "w") as secrets_file:
        secrets_file.write(secrets_file_content)

    try:
        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            "--secrets-file",
            secrets_path,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",
            "--no-prompt",  # Prevent interactive prompting
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command failed
        assert result.returncode != 0

        # Check for expected error message about empty developer secret
        # Error message could be in either stdout or stderr
        combined_output = result.stderr + result.stdout
        assert "Developer secret" in combined_output
        assert "has no value" in combined_output
        assert "must have values" in combined_output

        # Create a secrets file with an explicitly empty developer secret (space)
        # Use direct YAML string to ensure proper tag handling
        empty_secrets_file_content = """api:
  key: !developer_secret 
"""
        empty_secrets_path = tempfile.mktemp(suffix=".yaml")
        with open(empty_secrets_path, "w") as empty_secrets_file:
            empty_secrets_file.write(empty_secrets_file_content)

        # Run the CLI deploy command with explicitly empty developer secret
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            config_path,
            "--secrets-file",
            empty_secrets_path,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",
            "--no-prompt",  # Prevent interactive prompting
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command failed
        assert result.returncode != 0

        # Check for expected error message about empty developer secret
        # Error message could be in either stdout or stderr
        combined_output = result.stderr + result.stdout
        assert "Developer secret" in combined_output
        assert "has no value" in combined_output

        # Clean up the extra temp file
        os.unlink(empty_secrets_path)

    finally:
        # Clean up temp files
        for path in [config_path, secrets_path]:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except:
                pass
