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
    assert "--ignore-file" in clean_text
    assert "mcpacignore" in clean_text


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


def test_deploy_defaults_to_configured_app_name(runner, temp_config_dir):
    """Command should fall back to the config-defined name when none is provided."""

    config_path = temp_config_dir / MCP_CONFIG_FILENAME
    original_config = config_path.read_text()
    config_path.write_text("name: fixture-app\n" + original_config)

    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    async def mock_process_secrets(*args, **kwargs):
        with open(kwargs.get("output_path", output_path), "w", encoding="utf-8") as f:
            f.write("key: value\n")
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None

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
        result = runner.invoke(
            app,
            [
                "deploy",
                "--working-dir",
                temp_config_dir,
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
            ],
        )

    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"
    first_call = mock_client.get_app_id_by_name.await_args_list[0]
    assert first_call.args[0] == "fixture-app"


def test_deploy_defaults_to_directory_name_when_config_missing_name(
    runner, temp_config_dir
):
    """Fallback uses the default name when config doesn't define one."""

    config_path = temp_config_dir / MCP_CONFIG_FILENAME
    original_config = config_path.read_text()
    config_path.write_text(original_config)  # ensure no name present

    secrets_path = temp_config_dir / MCP_SECRETS_FILENAME
    if secrets_path.exists():
        secrets_path.unlink()

    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    async def mock_process_secrets(*args, **kwargs):
        with open(kwargs.get("output_path", output_path), "w", encoding="utf-8") as f:
            f.write("key: value\n")
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None

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
        result = runner.invoke(
            app,
            [
                "deploy",
                "--working-dir",
                temp_config_dir,
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
            ],
        )

    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"
    first_call = mock_client.get_app_id_by_name.await_args_list[0]
    assert first_call.args[0] == "default"


def test_deploy_uses_config_description_when_not_provided(runner, temp_config_dir):
    """If CLI description is omitted, reuse the config-defined description."""

    config_path = temp_config_dir / MCP_CONFIG_FILENAME
    original_config = config_path.read_text()
    config_path.write_text(
        "description: Configured app description\n" + original_config
    )

    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    async def mock_process_secrets(*args, **kwargs):
        with open(kwargs.get("output_path", output_path), "w", encoding="utf-8") as f:
            f.write("key: value\n")
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None

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
        result = runner.invoke(
            app,
            [
                "deploy",
                "--working-dir",
                temp_config_dir,
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
            ],
        )

    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"
    create_call = mock_client.create_app.await_args
    assert create_call.kwargs["description"] == "Configured app description"


def test_deploy_uses_defaults_when_config_cannot_be_loaded(runner, temp_config_dir):
    """If config parsing fails, fall back to default name and unset description."""

    config_path = temp_config_dir / MCP_CONFIG_FILENAME
    config_path.write_text("invalid: [\n")

    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    async def mock_process_secrets(*args, **kwargs):
        with open(kwargs.get("output_path", output_path), "w", encoding="utf-8") as f:
            f.write("key: value\n")
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None

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
        result = runner.invoke(
            app,
            [
                "deploy",
                "--working-dir",
                temp_config_dir,
                "--api-url",
                "http://test-api.com",
                "--api-key",
                "test-api-key",
                "--non-interactive",
            ],
        )

    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"
    name_call = mock_client.get_app_id_by_name.await_args_list[0]
    assert name_call.args[0] == "default"

    create_call = mock_client.create_app.await_args
    assert create_call.kwargs.get("description") is None


def test_deploy_auto_detects_mcpacignore(runner, temp_config_dir):
    """A `.mcpacignore` that lives beside the config dir is auto-detected.

    The CLI should discover the file without extra flags, resolve it to an
    absolute path, and hand that path through to `wrangler_deploy` so the
    bundler applies the expected ignore patterns.
    """
    default_ignore = temp_config_dir / ".mcpacignore"
    default_ignore.write_text("*.log\n")

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None
    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.create_app.return_value = mock_app

    captured = {}

    def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
        captured["ignore_file"] = ignore_file
        return MOCK_APP_ID

    async def _fake_process_config_secrets(*_args, **_kwargs):
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

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
            side_effect=_fake_process_config_secrets,
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
            ],
        )

    assert result.exit_code == 0, result.stdout
    ignore_path = captured.get("ignore_file")
    assert ignore_path is not None
    assert ignore_path.resolve() == default_ignore.resolve()


def test_deploy_uses_cwd_mcpacignore_when_config_dir_lacks_one(
    runner, temp_config_dir, monkeypatch
):
    """Fallback to the working directory's ignore file when config_dir has none.

    When the project directory does not contain `.mcpacignore`, the CLI should
    look in `Path.cwd()` and forward that file to the bundler, ensuring teams
    can keep ignore rules in the working tree root.
    """
    default_ignore = temp_config_dir / ".mcpacignore"
    if default_ignore.exists():
        default_ignore.unlink()

    with tempfile.TemporaryDirectory() as cwd_dir:
        cwd_path = Path(cwd_dir)
        monkeypatch.chdir(cwd_path)

        cwd_ignore = cwd_path / ".mcpacignore"
        cwd_ignore.write_text("*.tmp\n")

        mock_client = AsyncMock()
        mock_client.get_app_id_by_name.return_value = None
        mock_app = MagicMock()
        mock_app.appId = MOCK_APP_ID
        mock_client.create_app.return_value = mock_app

        captured = {}

        def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
            captured["ignore_file"] = ignore_file
            return MOCK_APP_ID

        async def _fake_process_config_secrets(*_args, **_kwargs):
            return {
                "deployment_secrets": [],
                "user_secrets": [],
                "reused_secrets": [],
                "skipped_secrets": [],
            }

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
                side_effect=_fake_process_config_secrets,
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
                ],
            )

        assert result.exit_code == 0, result.stdout
        ignore_path = captured.get("ignore_file")
        assert ignore_path is not None
        assert ignore_path.resolve() == cwd_ignore.resolve()


def test_deploy_no_ignore_when_file_missing(runner, temp_config_dir):
    """No ignore file is used when neither `.mcpacignore` nor `--ignore-file` exists.

    Ensures the CLI passes `None` to `wrangler_deploy`, meaning only the built-in
    exclusions run when there is no ignore file anywhere on disk.
    """
    default_ignore = temp_config_dir / ".mcpacignore"
    if default_ignore.exists():
        default_ignore.unlink()

    mock_client = AsyncMock()
    mock_client.get_app_id_by_name.return_value = None
    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.create_app.return_value = mock_app

    captured = {}

    def _capture_wrangler(app_id, api_key, project_dir, ignore_file=None):
        captured["ignore_file"] = ignore_file
        return MOCK_APP_ID

    async def _fake_process_config_secrets(*_args, **_kwargs):
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

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
            side_effect=_fake_process_config_secrets,
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
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert captured.get("ignore_file") is None


def test_deploy_ignore_file_custom(runner, temp_config_dir):
    """`--ignore-file` should win over auto-detection and stay intact.

    Confirms the CLI resolves the user-supplied path flag and forwards that
    absolute location to `wrangler_deploy` unmodified.
    """
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

    async def _fake_process_config_secrets(*_args, **_kwargs):
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

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
            side_effect=_fake_process_config_secrets,
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
    ignore_path = captured.get("ignore_file")
    assert ignore_path is not None
    assert ignore_path.resolve() == custom_ignore.resolve()


def test_deploy_ignore_file_overrides_default(runner, temp_config_dir):
    """`--ignore-file` overrides any `.mcpacignore` located on disk.

    With both files present, the bundler should receive the explicit flag’s
    path, proving that manual overrides take precedence over defaults.
    """
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

    async def _fake_process_config_secrets(*_args, **_kwargs):
        return {
            "deployment_secrets": [],
            "user_secrets": [],
            "reused_secrets": [],
            "skipped_secrets": [],
        }

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
            side_effect=_fake_process_config_secrets,
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
    ignore_path = captured.get("ignore_file")
    assert ignore_path is not None
    assert ignore_path.resolve() == custom_ignore.resolve()


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
