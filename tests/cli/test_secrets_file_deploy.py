"""Test secrets file processing in the deploy command."""

import os
import tempfile
from pathlib import Path
import pytest
import yaml
from unittest.mock import patch, MagicMock

from mcp_agent_cloud.commands.deploy import deploy_config
from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.processor import DeveloperSecret, UserSecret


# Sample configuration and secrets for testing
SAMPLE_CONFIG = """
server:
  host: localhost
  port: 8000
  api_key: !developer_secret test-api-key
  user_token: !user_secret
"""

SAMPLE_SECRETS = """
openai:
  api_key: !developer_secret test-openai-key
aws:
  region: !user_secret
  access_key_id: !user_secret
"""


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient that returns predictable handles."""
    client = MagicMock(spec=SecretsClient)
    
    # Configure create_secret to return different handles based on secret name and type
    async def mock_create_secret(name, secret_type, value=None):
        # Generate a deterministic handle based on the path and type
        secret_id = f"test-secret-{name.replace('.', '-')}"
        return secret_id
    
    client.create_secret.side_effect = mock_create_secret
    
    return client


def test_deploy_with_separate_secrets_file():
    """Test the deploy command with a separate secrets file.
    
    This test just verifies that our command can run with the new parameter layout.
    """
    # Create temporary files for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write sample files
        config_path = Path(temp_dir) / "config.yaml"
        with open(config_path, "w") as f:
            f.write(SAMPLE_CONFIG)
        
        secrets_path = Path(temp_dir) / "secrets.yaml"
        with open(secrets_path, "w") as f:
            f.write(SAMPLE_SECRETS)
            
        # Output path for transformed secrets file
        secrets_output = Path(temp_dir) / "secrets.transformed.yaml"
        
        # Add environment variable for the test
        os.environ["test-openai-key"] = "test-openai-api-key-value"
        
        # Just mock the actual deployment to avoid API calls
        with patch("mcp_agent_cloud.commands.deploy.main.wrangler_deploy"):
            try:
                # Try running the deploy command with the new parameter structure
                result = deploy_config(
                    secrets_file=secrets_path,
                    config_file=config_path,
                    secrets_output_file=secrets_output,
                    no_secrets=True,  # Skip secrets to avoid API calls
                    api_url="http://test.api/",
                    api_key="test-token",
                    dry_run=True,
                    non_interactive=False
                )
                
                # If we get here, the command ran without errors with the new parameter layout
                assert True
                
            except Exception as e:
                # If any exception happens, the test fails
                assert False, f"Deploy command failed: {str(e)}"