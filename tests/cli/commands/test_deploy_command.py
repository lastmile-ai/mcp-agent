"""Tests for the deploy command functionality in the CLI."""

import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_agent.cli.cloud.main import app
from mcp_agent.cli.core.constants import (
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
)
from mcp_agent.cli.mcp_app.mock_client import MOCK_APP_ID, MOCK_APP_NAME
from mcp_agent.cli.cloud.commands import deploy_config


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory with sample config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write sample config file
        config_content = """
server:
  host: localhost
  port: 8000
database:
  username: admin
"""
        config_path = Path(temp_dir) / MCP_CONFIG_FILENAME
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        # Write sample secrets file
        secrets_content = """
server:
  api_key: mock-server-api-key
database:
  user_token: mock-database-user-token
"""
        secrets_path = Path(temp_dir) / MCP_SECRETS_FILENAME
        with open(secrets_path, "w", encoding="utf-8") as f:
            f.write(secrets_content)

        yield Path(temp_dir)


def test_deploy_command_help(runner):
    """Test that the deploy command help displays expected arguments and options."""
    result = runner.invoke(app, ["deploy", "--help"])

    # Command should succeed
    assert result.exit_code == 0

    # remove all lines, dashes, etc
    ascii_text = re.sub(r"[^A-z0-9.,-]+", "", result.stdout)
    # remove any remnants of colour codes
    without_escape_codes = re.sub(r"\[[0-9 ]+m", "", ascii_text)
    # normalize spaces and convert to lower case
    clean_text = " ".join(without_escape_codes.split()).lower()

    # Expected options from the current deploy command
    assert "--config-dir" in clean_text or "-c" in clean_text
    assert "--api-url" in clean_text
    assert "--api-key" in clean_text
    assert "--non-interactive" in clean_text
    # New ignore options
    assert "--ignore" in clean_text
    assert "--ignore-file" in clean_text


def test_deploy_command_basic(runner, temp_config_dir):
    """Test the basic deploy command with mocked API client."""
    # Set up paths
    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    # Mock the process_config_secrets function to return a mock value
    async def mock_process_secrets(*args, **kwargs):
        # Write a mock transformed file
        with open(kwargs.get("output_path", output_path), "w", encoding="utf-8") as f:
            f.write("# Transformed file\ntest: value\n")
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    # Mock the MCP App Client with async methods
    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None  # No existing app

    # Mock the app object returned by create_app
    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.create_app.return_value = mock_app

    with (
        patch(
            "mcp_agent.cli.secrets.processor.process_config_secrets",
            side_effect=mock_process_secrets,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy",
            return_value=MOCK_APP_ID,
        ),
        ):
            # Run the deploy command
            result = runner.invoke(
                app,
                [
                    "deploy",
                    MOCK_APP_NAME,
                    "--config-dir",
                    temp_config_dir,
                    "--api-url",
                    "http://test-api.com",
                    "--api-key",
                    "test-api-key",
                    "--non-interactive",  # Prevent prompting for input
                ],
            )

    # Check command exit code
    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"

    # Verify the command was successful
    assert "Secrets file processed successfully" in result.stdout

    # Check for expected output file path
    assert "Transformed secrets file written to" in result.stdout


def test_deploy_ignore_uses_default_file(runner, temp_config_dir, monkeypatch):
    """Bare --ignore uses .mcpacignore in CWD."""
    # Create a dummy .mcpacignore in CWD by chdir to config dir
    with monkeypatch.context() as m:
        m.chdir(temp_config_dir)
        (temp_config_dir / ".mcpacignore").write_text("*.log\n")

        mock_client = AsyncMock()
        mock_client.get_app_id_by_name.return_value = None
        mock_app = MagicMock()
        mock_app.appId = MOCK_APP_ID
        mock_client.create_app.return_value = mock_app

        captured = {}

        def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
            captured["ignore_file"] = ignore_file
            return MOCK_APP_ID

        with (
            patch(
                "mcp_agent.cli.cloud.commands.deploy.main.MCPAppClient",
                return_value=mock_client,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy",
                side_effect=_capture_wrangler,
            ),
            patch(
                "mcp_agent.cli.secrets.processor.process_config_secrets",
                new_callable=AsyncMock,
                return_value={
                    "deployment_secrets": [],
                    "user_secrets": [],
                    "reused_secrets": [],
                    "skipped_secrets": [],
                },
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "deploy",
                    MOCK_APP_NAME,
                    "--config-dir",
                    str(temp_config_dir),
                    "--api-url",
                    "http://test-api.com",
                    "--api-key",
                    "test-api-key",
                    "--non-interactive",
                    "--ignore",
                ],
            )

        assert result.exit_code == 0, result.stdout
        assert captured.get("ignore_file") == Path(".mcpacignore")


def test_deploy_ignore_file_custom(runner, temp_config_dir):
    """--ignore-file passes the provided path through to bundler."""
    custom_ignore = temp_config_dir / ".deployignore"
    custom_ignore.write_text("*.tmp\n")

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None
    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.create_app.return_value = mock_app

    captured = {}

    def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
        captured["ignore_file"] = ignore_file
        return MOCK_APP_ID

    with (
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy",
            side_effect=_capture_wrangler,
        ),
        patch(
            "mcp_agent.cli.secrets.processor.process_config_secrets",
            new_callable=AsyncMock,
            return_value={
                "deployment_secrets": [],
                "user_secrets": [],
                "reused_secrets": [],
                "skipped_secrets": [],
            },
        ),
    ):
        result = runner.invoke(
            app,
            [
                "deploy",
                MOCK_APP_NAME,
                "--config-dir",
                str(temp_config_dir),
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
                "--ignore-file",
                str(custom_ignore),
            ],
        )

    assert result.exit_code == 0, result.stdout
    # Typer resolves path, so expect absolute
    assert captured.get("ignore_file") == custom_ignore.resolve()


def test_deploy_ignore_precedence_custom_over_default(runner, temp_config_dir):
    """When both provided, --ignore-file takes precedence over --ignore default."""
    default_ignore = temp_config_dir / ".mcpacignore"
    default_ignore.write_text("*.log\n")
    custom_ignore = temp_config_dir / ".customignore"
    custom_ignore.write_text("*.tmp\n")

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None
    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.create_app.return_value = mock_app

    captured = {}

    def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
        captured["ignore_file"] = ignore_file
        return MOCK_APP_ID

    with (
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy",
            side_effect=_capture_wrangler,
        ),
        patch(
            "mcp_agent.cli.secrets.processor.process_config_secrets",
            new_callable=AsyncMock,
            return_value={
                "deployment_secrets": [],
                "user_secrets": [],
                "reused_secrets": [],
                "skipped_secrets": [],
            },
        ),
    ):
        result = runner.invoke(
            app,
            [
                "deploy",
                MOCK_APP_NAME,
                "--config-dir",
                str(temp_config_dir),
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
                "--ignore",
                "--ignore-file",
                str(custom_ignore),
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert captured.get("ignore_file") == custom_ignore.resolve()


def test_deploy_with_secrets_file():
    """Test the deploy command with a secrets file."""
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a config file
        config_content = """
server:
  host: example.com
  port: 443
"""
        config_path = temp_path / MCP_CONFIG_FILENAME
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        # Create a secrets file
        secrets_content = """
server:
  api_key: mock-server-api-key
  user_token: mock-server-user-token
"""
        secrets_path = temp_path / MCP_SECRETS_FILENAME
        with open(secrets_path, "w", encoding="utf-8") as f:
            f.write(secrets_content)

        # Mock the MCP App Client and wrangler_deploy with async methods
        mock_client = AsyncMock()
        mock_client.get_app_id_by_name.return_value = None  # No existing app

        # Mock the app object returned by create_app
        mock_app = MagicMock()
        mock_app.appId = MOCK_APP_ID
        mock_client.create_app.return_value = mock_app

        with (
            patch(
                "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy",
                return_value=MOCK_APP_ID,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.deploy.main.MCPAppClient",
                return_value=mock_client,
            ),
        ):
            # Run the deploy command
            result = deploy_config(
                ctx=MagicMock(),
                app_name=MOCK_APP_NAME,
                app_description="A test MCP Agent app",
                config_dir=temp_path,
                api_url="http://test.api/",
                api_key="test-token",
                non_interactive=True,  # Set to True to avoid prompting
                retry_count=3,  # Add the missing retry_count parameter
            )

            # Verify deploy was successful
            secrets_output = temp_path / MCP_DEPLOYED_SECRETS_FILENAME
            assert os.path.exists(secrets_output), "Output file should exist"

            # Verify secrets file is unchanged
            with open(secrets_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert content == secrets_content, (
                    "Output file content should match original secrets"
                )

            # Verify the function deployed the correct mock app
            assert result == MOCK_APP_ID
