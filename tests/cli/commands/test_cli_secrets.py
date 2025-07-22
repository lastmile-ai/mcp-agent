"""Tests for the CLI's secrets handling functionality.

This file consolidates tests for the CLI's ability to process configuration files with secrets,
focusing on the deploy phase functionality.
"""

import os
import re
import subprocess
import tempfile
import uuid
from unittest.mock import patch

import pytest
from mcp_agent_cloud.core.constants import UUID_PATTERN, UUID_PREFIX


@pytest.fixture(scope="module")
def mock_api_credentials():
    """Mock API credentials for tests that use --dry-run and don't need a real API."""
    # These won't be used in dry-run mode but are required by the test
    return "http://mock-api-server.local", "mock-test-token"


@pytest.fixture
def setup_test_env_vars():
    """Set up environment variables for testing."""
    # Save original environment variables
    orig_env = os.environ.copy()

    # Add a test API key if not already set
    if "MCP_API_KEY" not in os.environ:
        os.environ["MCP_API_KEY"] = "test-api-key"

    yield

    # Restore original environment variables
    os.environ.clear()
    os.environ.update(orig_env)


def test_cli_deploy_with_secrets(mock_api_credentials, setup_test_env_vars):
    """Test the CLI deploy command with a configuration file containing secrets.

    This test uses --dry-run mode so it doesn't need a real API connection.
    """
    API_URL, API_TOKEN = mock_api_credentials

    # Set up env var for test-api-key to avoid interactive prompts
    os.environ["test-api-key"] = "dummy-api-key-value"

    # Create a temporary directory for the test
    test_dir = tempfile.mkdtemp()

    # Generate a unique test name
    test_name = f"test-cli-{uuid.uuid4().hex[:8]}"

    # Create a test config without secrets
    main_config = {
        "name": test_name,
        "server": {"host": "localhost", "port": 8080},
    }

    # Write the config to the temp directory with the expected name
    config_path = os.path.join(test_dir, "mcp_agent.config.yaml")
    with open(config_path, "w", encoding="utf-8") as config_file:
        import yaml

        yaml.dump(main_config, config_file)

    # Create a temporary secrets file with YAML string for proper tag handling
    secrets_file_content = """api:
  key: !developer_secret test-api-key
database:
  password: !user_secret
"""
    secrets_path = os.path.join(test_dir, "mcp_agent.secrets.yaml")
    with open(secrets_path, "w", encoding="utf-8") as secrets_file:
        secrets_file.write(secrets_file_content)

    try:
        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            test_dir,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Don't actually deploy
            "--non-interactive",  # Prevent interactive prompts
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # Check for expected success messages in output
        assert "Secrets file processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout

        # Verify the transformed secrets file exists
        secrets_output_path = os.path.join(test_dir, "mcp_agent.deployed.secrets.yaml")
        assert os.path.exists(secrets_output_path), (
            "Transformed secrets file was not created"
        )

        # Read the transformed secrets file as text
        with open(secrets_output_path, "r", encoding="utf-8") as f:
            transformed_yaml_text = f.read()

        print("\nTransformed YAML Content:")
        print(transformed_yaml_text)

        # Extract the UUID using a precise pattern based on the production format
        dev_secret_pattern = r"key:\s+(" + UUID_PATTERN.strip("^$") + ")"
        dev_match = re.search(dev_secret_pattern, transformed_yaml_text)
        assert dev_match is not None, (
            f"Developer secret with production UUID pattern not found in file"
        )

        # Validate the UUID format
        dev_uuid_str = dev_match.group(1)
        # Verify it starts with the correct prefix
        assert dev_uuid_str.startswith(UUID_PREFIX), (
            f"Expected {UUID_PREFIX} prefix, got: {dev_uuid_str}"
        )

        # Verify it matches our production UUID pattern exactly
        uuid_part = dev_uuid_str[len(UUID_PREFIX) :]
        try:
            # Should be a valid UUID according to the uuid module
            uuid.UUID(uuid_part)
            is_uuid = True
        except ValueError:
            is_uuid = False
        assert is_uuid, f"Expected standard UUID format after prefix, got: {uuid_part}"

        # Verify the user secret was NOT transformed and still has its tag
        user_secret_pattern = r"password:\s+!user_secret"
        user_match = re.search(user_secret_pattern, transformed_yaml_text)
        assert user_match is not None, f"User secret tag pattern not found in file"

    finally:
        # Clean up temp directory and all contents
        try:
            import shutil

            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except:
            pass


def test_cli_deploy_with_env_var_secret(mock_api_credentials, setup_test_env_vars):
    """Test the CLI deploy command with a secret from an environment variable."""
    API_URL, API_TOKEN = mock_api_credentials

    # Set a test environment variable
    env_var_name = f"MCP_TEST_SECRET_{uuid.uuid4().hex[:8]}".upper()
    secret_value = f"secret-value-{uuid.uuid4().hex[:8]}"
    os.environ[env_var_name] = secret_value

    # Create a temporary directory for the test
    test_dir = tempfile.mkdtemp()

    # Create a basic config file
    main_config = {"app": {"name": "env-var-test", "port": 9000}}

    # Write the config to the temp directory with the expected name
    config_path = os.path.join(test_dir, "mcp_agent.config.yaml")
    with open(config_path, "w", encoding="utf-8") as config_file:
        import yaml

        yaml.dump(main_config, config_file)

    # Create a temporary secrets file with environment variable reference
    # Use direct YAML string to ensure proper tag handling
    secrets_file_content = f"""api:
  key: !developer_secret {env_var_name}
"""
    secrets_path = os.path.join(test_dir, "mcp_agent.secrets.yaml")
    with open(secrets_path, "w", encoding="utf-8") as secrets_file:
        secrets_file.write(secrets_file_content)

    try:
        # The expected path for the transformed secrets output
        secrets_output_path = os.path.join(test_dir, "mcp_agent.deployed.secrets.yaml")

        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            test_dir,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Don't actually deploy
            "--non-interactive",  # Prevent interactive prompts
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
        with open(secrets_output_path, "r", encoding="utf-8") as f:
            transformed_yaml_text = f.read()

        # Verify the environment variable secret was transformed to a production-format UUID
        prod_pattern = UUID_PATTERN.strip(
            "^$"
        )  # Remove regex anchors for use in larger pattern
        assert (
            re.search(r"key:\s+(" + prod_pattern + ")", transformed_yaml_text)
            is not None
        ), "Expected production UUID format for transformed secret"

    finally:
        # Clean up temp directory and all contents
        try:
            import shutil

            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except:
            pass

        # Remove test environment variable
        if env_var_name in os.environ:
            del os.environ[env_var_name]


def test_cli_deploy_with_realistic_configs(mock_api_credentials, setup_test_env_vars):
    """Test secret processing with realistic agent configurations.

    Uses test fixtures with real-world configuration patterns and checks that:
    1. Developer secrets are transformed to UUIDs
    2. User secrets remain as tags

    This test uses the mock client with --dry-run mode, so it doesn't need
    a real API connection.
    """
    API_URL, API_TOKEN = mock_api_credentials

    # Create a temporary directory for the test
    test_dir = tempfile.mkdtemp()

    # Create a temporary config file for this test
    config_content = """
name: test-realistic-config
version: 1.0
models:
  openai:
    provider: openai
  anthropic:
    provider: anthropic
"""
    config_path = os.path.join(test_dir, "mcp_agent.config.yaml")
    with open(config_path, "w", encoding="utf-8") as config_file:
        config_file.write(config_content)

    # Create a temporary secrets file with multiple secrets
    secrets_content = """
models:
  openai:
    api_key: !developer_secret OPENAI_API_KEY
    organization_id: !user_secret OPENAI_ORG_ID
  anthropic:
    api_key: !developer_secret ANTHROPIC_API_KEY
"""
    secrets_path = os.path.join(test_dir, "mcp_agent.secrets.yaml")
    with open(secrets_path, "w", encoding="utf-8") as secrets_file:
        secrets_file.write(secrets_content)

    try:
        # Set some environment variables for the test
        os.environ.update(
            {
                "OPENAI_API_KEY": f"sk-test-{uuid.uuid4().hex[:8]}",
                "ANTHROPIC_API_KEY": f"sk-ant-test-{uuid.uuid4().hex[:8]}",
            }
        )

        # The expected path for the transformed secrets output
        secrets_output_path = os.path.join(test_dir, "mcp_agent.deployed.secrets.yaml")

        # Run the CLI deploy command
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            test_dir,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Don't actually deploy
            "--non-interactive",  # Prevent interactive prompts
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # Check for expected success messages
        assert "Secrets file processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout

        # Verify the transformed secrets file exists
        assert os.path.exists(secrets_output_path), (
            "Transformed secrets file was not created"
        )

        # Read the transformed file
        with open(secrets_output_path, "r", encoding="utf-8") as f:
            transformed_yaml = f.read()

        # Check developer secrets were transformed to production-format UUIDs
        # Both OpenAI and Anthropic keys should be properly formatted UUIDs
        prod_pattern = UUID_PATTERN.strip(
            "^$"
        )  # Remove regex anchors for use in larger pattern

        # API keys should be transformed to production-format UUIDs
        assert (
            re.search(r"api_key:\s+(" + prod_pattern + ")", transformed_yaml)
            is not None
        ), "Developer secret not transformed to production UUID format"

        # Count how many correctly formatted UUIDs are in the file (should match number of developer secrets)
        uuid_matches = re.findall(prod_pattern, transformed_yaml)
        assert len(uuid_matches) == 2, f"Expected 2 UUIDs, found {len(uuid_matches)}"

        # User secrets should remain as tags
        # Could have quotes around the value or not, depending on the YAML library's output
        assert (
            "organization_id: !user_secret OPENAI_ORG_ID" in transformed_yaml
            or "organization_id: !user_secret 'OPENAI_ORG_ID'" in transformed_yaml
        ), "User secret was incorrectly transformed"

    finally:
        # Clean up temp directory and all contents
        try:
            import shutil

            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except:
            pass

        # Clean up environment variables
        for var in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            if var in os.environ:
                del os.environ[var]


def test_cli_error_handling(mock_api_credentials):
    """Test the CLI error handling for invalid configs or missing credentials."""
    API_URL, API_TOKEN = mock_api_credentials

    # Create a temporary directory that doesn't exist
    nonexistent_dir = tempfile.mktemp()  # This is just a path that doesn't exist

    # Create a temporary directory for valid files
    test_dir = tempfile.mkdtemp()

    # Create valid config and secrets files
    config_path = os.path.join(test_dir, "mcp_agent.config.yaml")
    with open(config_path, "w", encoding="utf-8") as config_file:
        import yaml

        yaml.dump({"test": "config"}, config_file)

    secrets_path = os.path.join(test_dir, "mcp_agent.secrets.yaml")
    with open(secrets_path, "w", encoding="utf-8") as secrets_file:
        yaml.dump({"test": "no_tag"}, secrets_file)

    try:
        # Test with nonexistent directory
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            nonexistent_dir,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should fail because file doesn't exist
        assert result.returncode != 0

        # Error message should mention the file doesn't exist
        combined_output = result.stderr + result.stdout
        assert (
            "does not exist" in combined_output.lower()
            or "no such file" in combined_output.lower()
        )

        # Test with the secret value not having a tag
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            test_dir,  # Use the valid directory
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",  # Avoid actual deployment issues
        ]

        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        assert result.returncode == 1

        # It should mention using the tags
        combined_output = result.stderr + result.stdout
        assert (
            "secrets must be tagged with !developer_secret or !user_secret"
            in combined_output.lower()
        )

    finally:
        # Clean up temp directory and all contents
        try:
            import shutil

            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except:
            pass


def test_developer_secret_validation(mock_api_credentials):
    """Test validation that developer secrets must have values."""
    API_URL, API_TOKEN = mock_api_credentials

    # Create a temporary directory for the test
    test_dir = tempfile.mkdtemp()

    # Create a minimal config file
    config_content = "name: validation-test"
    config_path = os.path.join(test_dir, "mcp_agent.config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    # Create a secrets file with an empty developer secret
    empty_secret_content = """
# This has an empty developer secret
api:
  key: !developer_secret
"""
    secrets_path = os.path.join(test_dir, "mcp_agent.secrets.yaml")
    with open(secrets_path, "w", encoding="utf-8") as f:
        f.write(empty_secret_content)

    try:
        # Test with empty developer secret
        cmd = [
            "python",
            "-m",
            "mcp_agent_cloud.cli.main",
            "deploy",
            "Test App",
            "--config-dir",
            test_dir,
            "--api-url",
            API_URL,
            "--api-key",
            API_TOKEN,
            "--dry-run",
            "--non-interactive",  # Prevent interactive prompting
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should fail because developer secrets require values
        assert result.returncode != 0

        # Error message should explain the issue
        combined_output = result.stdout + result.stderr
        assert "Developer secret" in combined_output
        assert "has no value" in combined_output

        # Create a new temporary directory for the test with valid env var
        valid_test_dir = tempfile.mkdtemp()

        # Create config file
        valid_config_path = os.path.join(valid_test_dir, "mcp_agent.config.yaml")
        with open(valid_config_path, "w", encoding="utf-8") as f:
            f.write("name: valid-test")

        # Create a secrets file with a developer secret that has a valid env var
        valid_env_var_content = """
# This has a developer secret with a valid env var
api:
  key: !developer_secret TEST_API_KEY
"""
        valid_secrets_path = os.path.join(valid_test_dir, "mcp_agent.secrets.yaml")
        with open(valid_secrets_path, "w", encoding="utf-8") as f:
            f.write(valid_env_var_content)

        # Set the environment variable
        os.environ["TEST_API_KEY"] = "test-api-key-value"

        try:
            # Test with developer secret pointing to a valid env var
            cmd = [
                "python",
                "-m",
                "mcp_agent_cloud.cli.main",
                "deploy",
                "Test App",
                "--config-dir",
                valid_test_dir,
                "--api-url",
                API_URL,
                "--api-key",
                API_TOKEN,
                "--dry-run",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            # Should succeed
            assert result.returncode == 0

            # Should mention loading from environment variable
            assert (
                "Loaded secret value for api.key from environment variable TEST_API_KEY"
                in result.stdout
            )

            # The output file should be in the valid_test_dir with the .deployed.yaml suffix
            deployed_path = os.path.join(
                valid_test_dir, "mcp_agent.deployed.secrets.yaml"
            )
            # Verify output file exists and contains a UUID
            assert os.path.exists(deployed_path), (
                f"Expected deployed file not found at {deployed_path}"
            )
            with open(deployed_path, "r") as f:
                transformed = f.read()

            # Should have production-format UUID in the output
            prod_pattern = UUID_PATTERN.strip(
                "^$"
            )  # Remove regex anchors for use in larger pattern
            assert (
                re.search(r"key:\s+(" + prod_pattern + ")", transformed) is not None
            ), "Developer secret not transformed to production UUID format"

        finally:
            # Clean up
            try:
                import shutil

                if os.path.exists(valid_test_dir):
                    shutil.rmtree(valid_test_dir)
            except:
                pass

            if "TEST_API_KEY" in os.environ:
                del os.environ["TEST_API_KEY"]

    finally:
        # Clean up temp directory
        try:
            import shutil

            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except:
            pass
