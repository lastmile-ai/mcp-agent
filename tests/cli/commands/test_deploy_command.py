"""Tests for the deploy command functionality in the CLI."""

import os
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_agent.cli.cloud.commands.deploy.validation import (
    validate_entrypoint,
    validate_project,
)
from typer.testing import CliRunner

from mcp_agent.cli.cloud.main import app
from mcp_agent.cli.core.constants import (
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
)
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mock_client import MOCK_APP_ID, MOCK_APP_NAME


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

        # Write sample secrets file - only include secrets with env vars
        secrets_content = """
server:
  api_key: !developer_secret SERVER_API_KEY
database:
  user_token: !user_secret USER_TOKEN
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

    # Expected options from the updated CLAUDE.md spec
    assert "--config-dir" in clean_text or "-c" in clean_text
    assert "--api-url" in clean_text
    assert "--api-key" in clean_text
    assert "--non-interactive" in clean_text
    assert "--dry-run" in clean_text
    assert "--no-secrets" in clean_text


def test_deploy_command_basic(runner, temp_config_dir):
    """Test the basic deploy command with mocked secrets client."""
    # Set up paths
    output_path = temp_config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    # Mock the environment variables
    with patch.dict(
        os.environ,
        {"SERVER_API_KEY": "test-server-key", "MCP_API_KEY": "test-api-key"},
    ):
        # Mock the process_config_secrets function to return a dummy value
        async def mock_process_secrets(*args, **kwargs):
            # Write a dummy transformed file
            with open(
                kwargs.get("output_path", output_path), "w", encoding="utf-8"
            ) as f:
                f.write("# Transformed file\ntest: value\n")
            return {"developer_secrets": [], "user_secrets": []}

        with patch(
            "mcp_agent.cli.secrets.processor.process_config_secrets",
            side_effect=mock_process_secrets,
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
                    "--dry-run",  # Use dry run to avoid actual deployment
                    "--non-interactive",  # Prevent prompting for input
                ],
            )

    # Check command exit code
    assert result.exit_code == 0, f"Deploy command failed: {result.stdout}"

    # Verify the command was successful
    assert "Secrets file processed successfully" in result.stdout

    # Check for expected output file path and dry run mode
    assert "Transformed secrets file written to" in result.stdout
    assert "dry run" in result.stdout.lower()


def test_deploy_command_no_secrets(runner, temp_config_dir):
    """Test deploy command with --no-secrets flag when a secrets file DOES NOT exist."""
    # Run with --no-secrets flag and --dry-run to avoid real deployment
    with patch(
        "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy"
    ) as mock_deploy:
        # Mock the wrangler deployment
        mock_deploy.return_value = None

        secrets_file = Path(temp_config_dir) / MCP_SECRETS_FILENAME
        # Ensure the secrets file does not exist
        if secrets_file.exists():
            secrets_file.unlink()

        result = runner.invoke(
            app,
            [
                "deploy",
                MOCK_APP_NAME,
                "--config-dir",
                temp_config_dir,
                "--no-secrets",
                "--dry-run",  # Add dry-run mode
            ],
        )

    # Command should succeed
    assert result.exit_code == 0

    # Check output mentions skipping secrets
    assert "skipping secrets processing" in result.stdout.lower()


def test_deploy_command_no_secrets_with_existing_secrets(runner, temp_config_dir):
    """Test deploy command with --no-secrets flag when a secrets file DOES exist."""
    # Run with --no-secrets flag and --dry-run to avoid real deployment
    with patch(
        "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy"
    ) as mock_deploy:
        # Mock the wrangler deployment
        mock_deploy.return_value = None

        result = runner.invoke(
            app,
            [
                "deploy",
                MOCK_APP_NAME,
                "--config-dir",
                temp_config_dir,
                "--no-secrets",
                "--dry-run",  # Add dry-run mode
            ],
        )

    # Command should fail
    assert result.exit_code == 1

    # Check output mentions existing secrets file found
    assert "secrets file 'mcp_agent.secrets.yaml' found in" in result.stdout.lower()


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

        # Create a secrets file with developer and user secrets
        secrets_content = """
server:
  api_key: !developer_secret API_KEY
  user_token: !user_secret USER_TOKEN
"""
        secrets_path = temp_path / MCP_SECRETS_FILENAME
        with open(secrets_path, "w", encoding="utf-8") as f:
            f.write(secrets_content)

        # Call deploy_config with wrangler_deploy mocked
        with patch(
            "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy"
        ) as mock_deploy:
            # Mock wrangler_deploy to prevent actual deployment
            mock_deploy.return_value = None

            # Set a test env var
            with patch.dict(os.environ, {"API_KEY": "test-key"}):
                # Use the real deploy_config function
                from mcp_agent.cli.cloud.commands import deploy_config

                # Run the deploy command
                result = deploy_config(
                    ctx=MagicMock(),
                    app_name=MOCK_APP_NAME,
                    app_description="A test MCP Agent app",
                    config_dir=temp_path,
                    no_secrets=False,
                    api_url="http://test.api/",
                    api_key="test-token",
                    dry_run=True,
                    non_interactive=True,  # Set to True to avoid prompting
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


def test_deploy_with_missing_env_vars():
    """Test deploy with missing environment variables and non-interactive mode."""
    # Create a temporary directory for test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a config file
        config_path = temp_path / MCP_CONFIG_FILENAME
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("server:\n  host: example.com\n")

        # Create a secrets file with developer secret that needs prompting
        secrets_path = temp_path / MCP_SECRETS_FILENAME
        with open(secrets_path, "w", encoding="utf-8") as f:
            f.write("server:\n  api_key: !developer_secret MISSING_ENV_VAR\n")

        # Call the deploy_config function directly with missing env var
        from mcp_agent.cli.cloud.commands import deploy_config

        # Call with non_interactive=True, which should fail with CLIError
        with pytest.raises(CLIError):
            deploy_config(
                ctx=MagicMock(),
                app_name=MOCK_APP_NAME,
                app_description="A test MCP Agent app",
                config_dir=temp_path,
                no_secrets=False,
                api_url="http://test.api/",
                api_key="test-token",
                dry_run=True,
                non_interactive=True,  # This should cause failure with missing env var
            )


def test_rollback_secrets_file(temp_config_dir):
    """Test the secrets file is unchanged if wrangler deployment fails."""
    secrets_path = temp_config_dir / MCP_SECRETS_FILENAME
    with open(secrets_path, "r", encoding="utf-8") as f:
        pre_deploy_secrets_content = f.read()

    # Call deploy_config with wrangler_deploy mocked
    with patch(
        "mcp_agent.cli.cloud.commands.deploy.main.wrangler_deploy"
    ) as mock_deploy:
        # Mock wrangler_deploy to prevent actual deployment
        mock_deploy.side_effect = Exception("Deployment failed")

        # Set a test env var
        with patch.dict(os.environ, {"SERVER_API_KEY": "test-key"}):
            # Use the real deploy_config function
            from mcp_agent.cli.cloud.commands import deploy_config

            # Run the deploy command
            deploy_config(
                ctx=MagicMock(),
                app_name=MOCK_APP_NAME,
                app_description="A test MCP Agent app",
                config_dir=temp_config_dir,
                no_secrets=False,
                api_url="http://test.api/",
                api_key="test-token",
                dry_run=True,
                non_interactive=True,  # Set to True to avoid prompting
            )

        # Verify secrets file is unchanged
        with open(secrets_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert content == pre_deploy_secrets_content, (
                "Output file content should match original secrets"
            )


# Wrangler Wrapper Validation Tests


@pytest.fixture
def valid_project_dir():
    """Create a temporary directory with valid project structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create a valid main.py with MCPApp definition
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(
    name="test-app",
    description="A test MCP Agent"
)
"""
        main_py_path = project_path / "main.py"
        main_py_path.write_text(main_py_content)

        yield project_path


@pytest.fixture
def project_with_requirements():
    """Create a temporary directory with requirements.txt."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create requirements.txt
        (project_path / "requirements.txt").write_text(
            "requests==2.31.0\nnumpy==1.24.0"
        )

        yield project_path


@pytest.fixture
def project_with_poetry():
    """Create a temporary directory with poetry configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create pyproject.toml
        pyproject_content = """[tool.poetry]
name = "test-app"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
"""
        (project_path / "pyproject.toml").write_text(pyproject_content)

        # Create poetry.lock
        (project_path / "poetry.lock").write_text("# Poetry lock file content")

        yield project_path


@pytest.fixture
def project_with_uv():
    """Create a temporary directory with uv configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-app"
version = "0.1.0"
"""
        (project_path / "pyproject.toml").write_text(pyproject_content)

        # Create uv.lock
        (project_path / "uv.lock").write_text("# UV lock file content")

        yield project_path


def test_validate_project_success(valid_project_dir):
    """Test validate_project with a valid project structure."""
    # Should not raise any exceptions
    validate_project(valid_project_dir)


def test_validate_project_missing_directory():
    """Test validate_project with non-existent directory."""
    with pytest.raises(FileNotFoundError, match="Project directory .* does not exist"):
        validate_project(Path("/non/existent/path"))


def test_validate_project_missing_main_py():
    """Test validate_project with missing main.py."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        with pytest.raises(FileNotFoundError, match="Required file main.py is missing"):
            validate_project(project_path)


def test_validate_project_with_requirements_txt(project_with_requirements):
    """Test validate_project with requirements.txt dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_requirements)


def test_validate_project_with_poetry(project_with_poetry):
    """Test validate_project with poetry dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_poetry)


def test_validate_project_with_uv(project_with_uv):
    """Test validate_project with uv dependency management."""
    # Should not raise any exceptions
    validate_project(project_with_uv)


def test_validate_project_multiple_dependency_managers():
    """Test validate_project with multiple dependency management files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create multiple dependency files
        (project_path / "requirements.txt").write_text("requests==2.31.0")
        (project_path / "poetry.lock").write_text("# Poetry lock")

        with pytest.raises(
            ValueError,
            match="Multiple Python project dependency management files found",
        ):
            validate_project(project_path)


def test_validate_project_uv_without_pyproject():
    """Test validate_project with uv.lock but no pyproject.toml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create uv.lock without pyproject.toml
        (project_path / "uv.lock").write_text("# UV lock file")

        with pytest.raises(
            ValueError,
            match="Invalid uv project: uv.lock found without corresponding pyproject.toml",
        ):
            validate_project(project_path)


def test_validate_project_poetry_without_pyproject():
    """Test validate_project with poetry.lock but no pyproject.toml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create main.py
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")
"""
        (project_path / "main.py").write_text(main_py_content)

        # Create poetry.lock without pyproject.toml
        (project_path / "poetry.lock").write_text("# Poetry lock file")

        with pytest.raises(
            ValueError,
            match="Invalid poetry project: poetry.lock found without corresponding pyproject.toml",
        ):
            validate_project(project_path)


def test_validate_entrypoint_success(valid_project_dir):
    """Test validate_entrypoint with valid MCPApp definition."""
    entrypoint_path = valid_project_dir / "main.py"
    # Should not raise any exceptions
    validate_entrypoint(entrypoint_path)


def test_validate_entrypoint_missing_file():
    """Test validate_entrypoint with non-existent file."""
    with pytest.raises(FileNotFoundError, match="Entrypoint file .* does not exist"):
        validate_entrypoint(Path("/non/existent/main.py"))


def test_validate_entrypoint_no_mcp_app():
    """Test validate_entrypoint without MCPApp definition."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py without MCPApp
        main_py_content = """
def main():
    print("Hello, world!")

if __name__ == "__main__":
    main()
"""
        main_py_path.write_text(main_py_content)

        with pytest.raises(ValueError, match="No MCPApp definition found in main.py"):
            validate_entrypoint(main_py_path)


def test_validate_entrypoint_with_main_block_warning(capsys):
    """Test validate_entrypoint with __main__ block shows warning."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py with MCPApp and __main__ block
        main_py_content = """from mcp_agent_cloud import MCPApp

app = MCPApp(name="test-app")

if __name__ == "__main__":
    print("This will be ignored")
"""
        main_py_path.write_text(main_py_content)

        # Should not raise exception but should print warning
        validate_entrypoint(main_py_path)

        # Check if warning was printed to stderr
        captured = capsys.readouterr()
        assert (
            "Found a __main__ entrypoint in main.py. This will be ignored"
            in captured.err
            or "Found a __main__ entrypoint in main.py. This will be ignored"
            in captured.out
        )


def test_validate_entrypoint_multiline_mcp_app():
    """Test validate_entrypoint with multiline MCPApp definition."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Create main.py with multiline MCPApp
        main_py_content = """from mcp_agent_cloud import MCPApp

my_app = MCPApp(
    name="test-app",
    description="A test application",
    version="1.0.0"
)
"""
        main_py_path.write_text(main_py_content)

        # Should not raise any exceptions
        validate_entrypoint(main_py_path)


def test_validate_entrypoint_different_variable_names():
    """Test validate_entrypoint with different variable names for MCPApp."""
    with tempfile.TemporaryDirectory() as temp_dir:
        main_py_path = Path(temp_dir) / "main.py"

        # Test various variable names
        for var_name in ["app", "my_app", "application", "mcp_app"]:
            main_py_content = f"""from mcp_agent_cloud import MCPApp

{var_name} = MCPApp(name="test-app")
"""
            main_py_path.write_text(main_py_content)

            # Should not raise any exceptions
            validate_entrypoint(main_py_path)
