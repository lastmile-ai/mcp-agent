"""Integration tests for secrets handling in the CLI.

These tests focus on the CLI's ability to process configuration files with secrets.
These tests are designed to work with the mock client by default (using --dry-run mode),
so they don't require a real API connection to run.

The tests are organized to check:
1. Basic processing of realistic configs (mock only)
2. Handling of mixed developer and user secrets (mock only)
3. Error handling for invalid inputs and missing credentials (mock only)
"""

import os
import re
import uuid
import tempfile
import subprocess
from pathlib import Path
import pytest

# Import fixtures from conftest
from tests.integration.conftest import FIXTURES_BASE

# Mark all tests in this module with the integration and mock markers
pytestmark = [pytest.mark.integration, pytest.mark.mock]


def test_cli_deploy_with_realistic_configs(mock_api_credentials, setup_test_env_vars):
    """Test secret processing with realistic agent configurations.
    
    Uses the pre-defined realistic configs from fixtures and checks that:
    1. Developer secrets are transformed to UUIDs
    2. User secrets remain as tags
    
    This test uses the mock client with --dry-run mode, so it doesn't need
    a real API connection.
    """
    API_URL, API_TOKEN = mock_api_credentials
    
    # Use the basic agent config from fixtures
    config_path = FIXTURES_BASE / "basic_agent" / "mcp_agent.config.yaml"
    secrets_path = FIXTURES_BASE / "basic_agent" / "mcp_agent.secrets.yaml"
    
    # Create a temporary file for the transformed output
    output_path = Path(tempfile.mktemp(suffix=".yaml"))
    
    try:
        # Set some environment variables for the test
        os.environ.update({
            "OPENAI_API_KEY": f"sk-test-{uuid.uuid4().hex[:8]}",
            "ANTHROPIC_API_KEY": f"sk-ant-test-{uuid.uuid4().hex[:8]}"
        })
        
        # Run the CLI command
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            "--secrets-file", str(secrets_path),
            "--secrets-output-file", str(output_path),
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"  # Don't actually deploy
        ]
        
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"
        
        # Check for expected success messages
        assert "Secrets file processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout
        
        # Verify the transformed secrets file exists
        assert output_path.exists(), "Transformed secrets file was not created"
        
        # Read the transformed file
        transformed_yaml = output_path.read_text()
        print("\nTransformed basic agent secrets:")
        print(transformed_yaml)
        
        # Check developer secrets were transformed to UUIDs
        # Both OpenAI and Anthropic keys should be UUIDs now
        uuid_pattern = r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'
        
        assert re.search(r'api_key:\s+' + uuid_pattern, transformed_yaml) is not None, \
            "Developer secret not transformed to UUID"
        
        # Count how many UUIDs are in the file (should match number of developer secrets)
        uuid_matches = re.findall(uuid_pattern, transformed_yaml)
        assert len(uuid_matches) == 2, f"Expected 2 UUIDs, found {len(uuid_matches)}"
        
    finally:
        # Clean up
        if output_path.exists():
            output_path.unlink()
            
        # Clean up environment variables
        for var in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            if var in os.environ:
                del os.environ[var]


def test_cli_deploy_with_mixed_secrets(mock_api_credentials, setup_test_env_vars):
    """Test secret processing with a mix of developer and user secrets.
    
    Uses the advanced agent config from fixtures and checks that:
    1. Developer secrets are transformed to UUIDs
    2. User secrets remain as tags
    
    This test uses the mock client with --dry-run mode, so it doesn't need
    a real API connection.
    """
    API_URL, API_TOKEN = mock_api_credentials
    
    # Use the advanced agent config from fixtures (has both dev and user secrets)
    config_path = FIXTURES_BASE / "advanced_agent" / "mcp_agent.config.yaml"
    secrets_path = FIXTURES_BASE / "advanced_agent" / "mcp_agent.secrets.yaml"
    
    # Create a temporary file for the transformed output
    output_path = Path(tempfile.mktemp(suffix=".yaml"))
    
    try:
        # Set some environment variables for the test
        os.environ.update({
            "OPENAI_API_KEY": f"sk-test-{uuid.uuid4().hex[:8]}",
            "ANTHROPIC_API_KEY": f"sk-ant-test-{uuid.uuid4().hex[:8]}",
            "AWS_ACCESS_KEY_ID": f"AKIA{uuid.uuid4().hex[:16].upper()}",
            "AWS_SECRET_ACCESS_KEY": f"aws-secret-{uuid.uuid4().hex}",
            "DB_USER": "testuser",
            "DB_PASSWORD": "testpassword"
        })
        
        # Run the CLI command
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            "--secrets-file", str(secrets_path),
            "--secrets-output-file", str(output_path),
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"  # Don't actually deploy
        ]
        
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Verify the command executed successfully
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"
        
        # Check for expected success messages
        assert "Secrets file processed successfully" in result.stdout
        assert "Deployment preparation completed successfully" in result.stdout
        
        # Verify the transformed secrets file exists
        assert output_path.exists(), "Transformed secrets file was not created"
        
        # Read the transformed file
        transformed_yaml = output_path.read_text()
        print("\nTransformed advanced agent secrets:")
        print(transformed_yaml)
        
        # Count developer secrets (should be 6: OpenAI API key, Anthropic API key, 
        # AWS access key, AWS secret key, DB user, DB password)
        uuid_pattern = r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'
        uuid_matches = re.findall(uuid_pattern, transformed_yaml)
        assert len(uuid_matches) == 6, f"Expected 6 UUIDs, found {len(uuid_matches)}"
        
        # Check user secrets were retained (3: OpenAI org ID, AWS session token, DB SSL cert)
        assert "organization_id: !user_secret" in transformed_yaml, \
            "User secret for organization_id was incorrectly transformed"
        assert "session_token: !user_secret" in transformed_yaml, \
            "User secret for session_token was incorrectly transformed"
        assert "ssl_cert: !user_secret" in transformed_yaml, \
            "User secret for ssl_cert was incorrectly transformed"
        
    finally:
        # Clean up
        if output_path.exists():
            output_path.unlink()
            
        # Clean up environment variables
        env_vars = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", 
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "DB_USER", "DB_PASSWORD"
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]


def test_cli_error_handling(mock_api_credentials):
    """Test CLI's error handling for invalid inputs and missing secrets file.
    
    This test doesn't need any real API connection and focuses on command-line
    parameter validation.
    """
    API_URL, API_TOKEN = mock_api_credentials

    # Create a simple config file
    config_content = """
name: test-config
version: 1.0
"""
    config_path = Path(tempfile.mktemp(suffix=".yaml"))
    config_path.write_text(config_content)
    
    # Create a simple secrets file
    secrets_content = """
# This is a test secrets file with no actual secrets
test: value
"""
    secrets_path = Path(tempfile.mktemp(suffix=".yaml"))
    secrets_path.write_text(secrets_content)
    
    try:
        # Test Case 1: Test with a non-existent secrets file
        non_existent_path = "/tmp/file-that-does-not-exist-192873465.yaml"
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            "--secrets-file", non_existent_path,
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Should fail because file doesn't exist
        assert result.returncode != 0
        
        # Error message should mention the file doesn't exist
        combined_output = result.stderr + result.stdout
        assert "does not exist" in combined_output.lower() or "no such file" in combined_output.lower()
        
        # Test Case 2: Missing secrets file
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            # No secrets-file parameter
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Should fail due to missing required parameter
        assert result.returncode != 0
        
        # Error should mention missing option
        assert "missing option" in result.stderr.lower()
        
    finally:
        # Clean up temp files
        for path in [config_path, secrets_path]:
            if path.exists():
                path.unlink()


def test_developer_secret_validation(mock_api_credentials):
    """Test validation that developer secrets must have values.
    
    This test verifies that the CLI properly validates developer secrets
    and fails when they have no value.
    
    This uses --dry-run mode with a mock client, so it doesn't need a real API.
    """
    API_URL, API_TOKEN = mock_api_credentials

    # Create a minimal config file
    config_content = "name: validation-test"
    config_path = Path(tempfile.mktemp(suffix=".yaml"))
    config_path.write_text(config_content)
    
    # Create a secrets file with an empty developer secret
    empty_secret_content = """
# This has an empty developer secret
api:
  key: !developer_secret
"""
    secrets_path = Path(tempfile.mktemp(suffix=".yaml"))
    secrets_path.write_text(empty_secret_content)
    
    # Create another secrets file with a developer secret that has a space (still empty)
    space_secret_content = """
# This has a developer secret with just a space (still empty)
api:
  key: !developer_secret 
"""
    space_secrets_path = Path(tempfile.mktemp(suffix=".yaml"))
    space_secrets_path.write_text(space_secret_content)
    
    try:
        # Test with empty developer secret
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            "--secrets-file", str(secrets_path),
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run",
            "--no-prompt"  # Prevent interactive prompting
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Should fail because developer secrets require values
        assert result.returncode != 0
        
        # Error message should explain the issue
        combined_output = result.stdout + result.stderr
        assert "Developer secret" in combined_output
        assert "has no value" in combined_output
        
        # Test with developer secret containing just a space
        cmd = [
            "python", "-m", "mcp_agent_cloud.cli.main", "deploy",
            str(config_path),
            "--secrets-file", str(space_secrets_path),
            "--api-url", API_URL,
            "--api-token", API_TOKEN,
            "--dry-run",
            "--no-prompt"  # Prevent interactive prompting
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Should also fail for the same reason
        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        assert "Developer secret" in combined_output
        assert "has no value" in combined_output
        
    finally:
        # Clean up temp files
        for path in [config_path, secrets_path, space_secrets_path]:
            if path.exists():
                path.unlink()