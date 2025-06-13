"""Test secrets file processing in the deploy command."""

import os
import tempfile
from pathlib import Path
from typing import Optional, Union
import pytest
import yaml
from unittest.mock import patch, MagicMock

from mcp_agent_cloud.commands.deploy import deploy_config
from mcp_agent_cloud.mcp_app.mock_client import (
    MOCK_APP_NAME,
    MOCK_APP_ID,
)
from mcp_agent_cloud.secrets.api_client import SecretsClient
from mcp_agent_cloud.secrets.yaml_tags import (
    load_yaml_with_secrets,
)

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
  api_key: !developer_secret TEST_OPENAI_API_KEY
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

    This test directly patches process_config_secrets to create the transformed secrets file.
    """
    # Create temporary files for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write sample files
        config_path = Path(temp_dir) / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_CONFIG)

        secrets_path = Path(temp_dir) / "secrets.yaml"
        with open(secrets_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_SECRETS)

        # Output path for transformed secrets file
        secrets_output = Path(temp_dir) / "secrets.transformed.yaml"

        # Create a transformed secrets file to simulate the processor's output
        transformed_secrets = {
            "openai": {"api_key": "test-secret-openai-api-key"},
            "aws": {
                "region": "test-secret-aws-region",
                "access_key_id": "test-secret-aws-access-key-id",
            },
        }

        with patch.dict(os.environ, {"TEST_OPENAI_API_KEY": "test-api-key"}):
            # Patch process_config_secrets to create the output file
            def transform_secrets(
                config_path: Union[str, Path],
                output_path: Optional[Union[str, Path]] = None,
                client: Optional[SecretsClient] = None,
                api_url: Optional[str] = None,
                api_key: Optional[str] = None,
                non_interactive: bool = False,
            ):
                print("PATCH!")
                with open(secrets_output, "w", encoding="utf-8") as f:
                    yaml.dump(transformed_secrets, f)
                return None

            with patch(
                "mcp_agent_cloud.commands.deploy.main.process_config_secrets",
                side_effect=transform_secrets,
            ):
                # Run the deploy command
                result = deploy_config(
                    app_name=MOCK_APP_NAME,
                    app_description="A test MCP Agent app",
                    config_file=config_path,
                    secrets_file=secrets_path,
                    secrets_output_file=secrets_output,
                    no_secrets=False,  # Explicitly set to process secrets
                    api_url="http://test.api/",
                    api_key="test-token",
                    dry_run=True,
                )

                # Verify the result is the deployed app id
                assert result == MOCK_APP_ID

                # Verify that the secrets file was processed (exists because our mock created it)
                assert (
                    secrets_output.exists()
                ), "Transformed secrets file should exist"

                # Load and check transformed secrets file
                with open(secrets_output, "r", encoding="utf-8") as f:
                    content = f.read()
                    loaded_secrets = load_yaml_with_secrets(content)

                # Check that secrets match what our mock created
                assert loaded_secrets == transformed_secrets
