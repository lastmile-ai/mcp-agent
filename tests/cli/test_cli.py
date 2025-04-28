"""Tests for the CLI."""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from mcp_agent_cloud.cli.main import app


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


def test_deploy_command_help(runner):
    """Test the deploy --help command."""
    result = runner.invoke(app, ["deploy", "--help"])
    assert result.exit_code == 0
    assert "Deploy an MCP agent" in result.stdout
    
    # Check parameters are in the help text - updated for dedicated secrets file approach
    assert "--api-url" in result.stdout
    assert "--api-token" in result.stdout
    assert "--secrets-file" in result.stdout
    assert "--secrets-output-file" in result.stdout
    assert "--no-secrets" in result.stdout
    assert "--dry-run" in result.stdout