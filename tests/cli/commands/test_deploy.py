"""Tests for the deploy command."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_agent_cloud.commands.deploy import deploy_config


def test_deploy_config_no_secrets(sample_config_yaml, sample_secrets_yaml, tmp_path):
    """Test deploy_config with no_secrets=True."""
    
    # Deploy with no_secrets=True should just skip processing
    with patch("mcp_agent_cloud.secrets.processor.process_config_secrets") as mock_process:
        result = deploy_config(
            config_file=Path(sample_config_yaml),
            secrets_file=Path(sample_secrets_yaml),
            no_secrets=True,
            dry_run=True,
        )
        
        # Should not have called process_config_secrets
        mock_process.assert_not_called()
        
        # Should return the original config path
        assert result == sample_config_yaml


def test_deploy_config_with_secrets(sample_config_yaml, sample_secrets_yaml, tmp_path):
    """Test deploy_config with secrets processing."""
    secrets_output_path = tmp_path / "output_secrets.yaml"
    
    # We need to patch the settings module first to override the default behavior
    with patch("mcp_agent_cloud.config.settings") as mock_settings:
        # Ensure settings.API_BASE_URL and settings.API_KEY are empty
        # so we rely only on the parameters
        mock_settings.API_BASE_URL = ""
        mock_settings.API_KEY = ""
        
        # Then mock the _run_async function
        with patch("mcp_agent_cloud.commands.deploy.main._run_async") as mock_run_async:
            # Call deploy_config with explicit no_secrets=False to ensure processing
            result = deploy_config(
                config_file=Path(sample_config_yaml),
                secrets_file=Path(sample_secrets_yaml),
                secrets_output_file=Path(secrets_output_path),
                no_secrets=False,  # Explicitly set to process secrets
                api_url="http://test-api",
                api_key="test-token",
                dry_run=True,
            )
            
            # Should have called _run_async once
            mock_run_async.assert_called_once()
            
            # Get the coroutine that was passed to _run_async
            coro_arg = mock_run_async.call_args[0][0]
            
            # The coroutine should be a call to process_config_secrets
            # Can't directly introspect the coroutine, but we can check its representation
            coro_str = str(coro_arg)
            assert "process_config_secrets" in coro_str
            
            # Check that result is the path to the original config (not transformed)
            assert result == str(sample_config_yaml)