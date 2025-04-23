"""Tests for the deploy command."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_agent_cloud.commands.deploy import deploy_config
from mcp_agent_cloud.secrets.constants import SecretsMode


def test_deploy_config_no_secrets(sample_config_yaml, tmp_path):
    """Test deploy_config with no_secrets=True."""
    output_path = tmp_path / "output.yaml"
    
    # Deploy with no_secrets=True should just skip processing
    with patch("mcp_agent_cloud.commands.deploy.process_config_secrets") as mock_process:
        result = deploy_config(
            config_file=Path(sample_config_yaml),
            no_secrets=True,
            dry_run=True,
        )
        
        # Should not have called process_config_secrets
        mock_process.assert_not_called()
        
        # Should return the original config path
        assert result == sample_config_yaml