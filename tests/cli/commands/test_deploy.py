"""Tests for the deploy command."""

from pathlib import Path
from unittest.mock import patch

from mcp_agent_cloud.commands.deploy import deploy_config
from mcp_agent_cloud.mcp_app.mock_client import (
    MOCK_APP_NAME,
    MOCK_APP_ID,
)


def test_deploy_config_no_secrets(sample_config_yaml, sample_secrets_yaml):
    """Test deploy_config with no_secrets=True."""

    # Deploy with no_secrets=True should just skip processing
    with patch(
        "mcp_agent_cloud.secrets.processor.process_config_secrets"
    ) as mock_process:
        result = deploy_config(
            app_name=MOCK_APP_NAME,
            app_description="A test MCP Agent app",
            config_file=Path(sample_config_yaml),
            secrets_file=Path(sample_secrets_yaml),
            no_secrets=True,
            dry_run=True,
        )

        # Should not have called process_config_secrets
        mock_process.assert_not_called()

        # Should return the mock app ID
        assert result == MOCK_APP_ID


def test_deploy_config_with_secrets(
    sample_config_yaml, sample_secrets_yaml, tmp_path
):
    """Test deploy_config with secrets processing."""
    secrets_output_path = tmp_path / "output_secrets.yaml"

    # We need to patch the settings module first to override the default behavior
    with patch("mcp_agent_cloud.config.settings") as mock_settings:
        # Ensure settings.API_BASE_URL and settings.API_KEY are empty
        # so we rely only on the parameters
        mock_settings.API_BASE_URL = ""
        mock_settings.API_KEY = ""

        result = deploy_config(
            app_name=MOCK_APP_NAME,
            app_description="A test MCP Agent app",
            config_file=Path(sample_config_yaml),
            secrets_file=Path(sample_secrets_yaml),
            secrets_output_file=Path(secrets_output_path),
            no_secrets=False,  # Explicitly set to process secrets
            api_url="http://test-api",
            api_key="test-token",
            dry_run=True,
        )

        # Should return the mock app ID
        assert result == MOCK_APP_ID

        # Verify file exists
        assert (
            secrets_output_path.exists()
        ), "Output file should have been created"

        # Read the file to verify it was written with transformed content
        with open(secrets_output_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert content, "Output file should not be empty"
