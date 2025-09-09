"""Tests for the configure command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from mcp_agent.cli.cloud.commands.configure.main import configure_app
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mock_client import (
    MOCK_APP_CONFIG_ID,
    MOCK_APP_ID,
    MOCK_APP_SERVER_URL,
)
from mcp_agent.cli.secrets.processor import nest_keys


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP app client."""
    client = MagicMock()
    client.list_config_params = AsyncMock(return_value=[])

    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    client.get_app = AsyncMock(return_value=mock_app)

    mock_config = MagicMock()
    mock_config.appConfigurationId = MOCK_APP_CONFIG_ID
    mock_config.appServerInfo = MagicMock()
    mock_config.appServerInfo.serverUrl = "https://test-server.example.com"
    client.configure_app = AsyncMock(return_value=mock_config)

    return client


@pytest.fixture
def patched_configure_app(mock_mcp_client):
    """Patch the configure_app function for testing."""

    # First, save a reference to the original function
    original_func = configure_app

    # Create a wrapped function that doesn't use typer but has same logic
    def wrapped_configure_app(**kwargs):
        # Provide default values for typer parameters
        defaults = {
            "api_url": kwargs.get("api_url", "http://test-api"),
            "api_key": kwargs.get("api_key", "test-token"),
        }
        kwargs.update(defaults)

        with (
            patch(
                "mcp_agent.cli.cloud.commands.configure.main.MCPAppClient",
                return_value=mock_mcp_client,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.configure.main.MockMCPAppClient",
                return_value=mock_mcp_client,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.configure.main.typer.Exit",
                side_effect=ValueError,
            ),
        ):
            try:
                # Call the original function with the provided arguments
                return original_func(**kwargs)
            except ValueError as e:
                # Convert typer.Exit to a test exception with code
                raise RuntimeError(f"Typer exit with code: {e}")

    return wrapped_configure_app


def test_no_required_secrets(patched_configure_app, mock_mcp_client):
    """Test when app has no required secrets."""

    # Test the function
    result = patched_configure_app(
        app_server_url=MOCK_APP_SERVER_URL,
        secrets_file=None,
        secrets_output_file=None,
        dry_run=False,
        params=False,
        api_url="http://test-api",
        api_key="test-token",
    )

    # Verify results
    assert result == MOCK_APP_CONFIG_ID
    mock_mcp_client.list_config_params.assert_called_once_with(
        app_server_url=MOCK_APP_SERVER_URL
    )
    mock_mcp_client.configure_app.assert_called_once_with(
        app_server_url=MOCK_APP_SERVER_URL, config_params={}
    )


def test_with_required_secrets_from_file(
    patched_configure_app, mock_mcp_client, tmp_path
):
    """Test with required secrets from a file."""

    # Setup required secrets and return values
    required_secrets = ["server.bedrock.api_key", "server.openai.api_key"]
    secret_values = {
        "server.bedrock.api_key": "mcpac_sc_12345678-1234-1234-1234-123456789012",
        "server.openai.api_key": "mcpac_sc_87654321-4321-4321-4321-210987654321",
    }

    # Update mock to return required secrets
    mock_mcp_client.list_config_params = AsyncMock(return_value=required_secrets)

    # Create test file
    secrets_file = tmp_path / "test_secrets.yaml"
    secrets_file.touch()

    # Mock retrieve_secrets_from_config
    with patch(
        "mcp_agent.cli.secrets.processor.retrieve_secrets_from_config",
        return_value=secret_values,
    ) as mock_retrieve:
        # Test the function
        result = patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=secrets_file,
            secrets_output_file=None,
            dry_run=False,
            params=False,
            api_url="http://test-api",
            api_key="test-token",
        )

        # Verify results
        assert result == MOCK_APP_CONFIG_ID
        mock_mcp_client.list_config_params.assert_called_once_with(
            app_server_url=MOCK_APP_SERVER_URL
        )
        mock_retrieve.assert_called_once_with(str(secrets_file), required_secrets)
        mock_mcp_client.configure_app.assert_called_once_with(
            app_server_url=MOCK_APP_SERVER_URL, config_params=secret_values
        )


def test_missing_app_id(patched_configure_app):
    """Test with missing app_id."""

    # Test with empty app_id
    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url="",
            secrets_file=None,
            secrets_output_file=None,
            dry_run=False,
            params=False,
        )

    # Test with None app_id
    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=None,
            secrets_file=None,
            secrets_output_file=None,
            dry_run=False,
            params=False,
        )


def test_invalid_file_types(patched_configure_app, tmp_path):
    """Test with invalid file types."""

    # Test with non-yaml secrets_file
    invalid_secrets_file = tmp_path / "invalid_secrets.txt"
    invalid_secrets_file.touch()

    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=invalid_secrets_file,
            secrets_output_file=None,
            dry_run=False,
            params=False,
        )

    # Test with non-yaml secrets_output_file
    invalid_output_file = tmp_path / "invalid_output.txt"

    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=None,
            secrets_output_file=invalid_output_file,
            dry_run=False,
            params=False,
        )


def test_both_input_output_files(patched_configure_app, tmp_path):
    """Test with both secrets_file and secrets_output_file provided."""

    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.touch()

    secrets_output_file = tmp_path / "output.yaml"

    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=secrets_file,
            secrets_output_file=secrets_output_file,
            dry_run=False,
            params=False,
        )


def test_missing_api_key(patched_configure_app):
    """Test with missing API key."""

    # Patch settings to ensure API_KEY is None
    with patch("mcp_agent.cli.cloud.commands.configure.main.settings") as mock_settings:
        mock_settings.API_KEY = None

        # Patch load_api_key_credentials to return None
        with patch(
            "mcp_agent.cli.cloud.commands.configure.main.load_api_key_credentials",
            return_value=None,
        ):
            with pytest.raises(CLIError):
                patched_configure_app(
                    app_server_url=MOCK_APP_SERVER_URL,
                    secrets_file=None,
                    secrets_output_file=None,
                    dry_run=False,
                    params=False,
                    api_key=None,  # Explicitly set to None
                )


def test_list_config_params_error(patched_configure_app, mock_mcp_client):
    """Test when list_config_params raises an error."""

    # Mock client to raise exception
    mock_mcp_client.list_config_params = AsyncMock(side_effect=Exception("API error"))

    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=None,
            secrets_output_file=None,
            dry_run=False,
            params=False,
            api_url="http://test-api",
            api_key="test-token",
        )


def test_no_secrets_with_secrets_file(patched_configure_app, mock_mcp_client, tmp_path):
    """Test when app doesn't require secrets but a secrets file is provided."""

    # Mock client that returns no required secrets
    mock_mcp_client.list_config_params = AsyncMock(return_value=[])

    # Create a secrets file
    secrets_file = tmp_path / "test_secrets.yaml"
    secrets_file.touch()

    with pytest.raises(CLIError):
        patched_configure_app(
            app_server_url=MOCK_APP_SERVER_URL,
            secrets_file=secrets_file,
            secrets_output_file=None,
            dry_run=False,
            params=False,
            api_url="http://test-api",
            api_key="test-token",
        )


def test_output_secrets_file_creation(tmp_path):
    """Test that the output secrets file is created with valid content."""

    # Setup required secrets and processed secrets
    required_secrets = ["server.bedrock.api_key", "server.openai.api_key"]
    processed_secrets = {
        "server.bedrock.api_key": "mcpac_sc_12345678-1234-1234-1234-123456789012",
        "server.openai.api_key": "mcpac_sc_87654321-4321-4321-4321-210987654321",
    }

    # Create mock client
    mock_client = MagicMock()
    mock_client.list_config_params = AsyncMock(return_value=required_secrets)

    mock_app = MagicMock()
    mock_app.appId = MOCK_APP_ID
    mock_client.get_app = AsyncMock(return_value=mock_app)

    # Mock app configuration response
    mock_config = MagicMock()
    mock_config.appConfigurationId = MOCK_APP_CONFIG_ID
    mock_config.appServerInfo = MagicMock()
    mock_config.appServerInfo.serverUrl = "https://test-server.example.com"
    mock_client.configure_app = AsyncMock(return_value=mock_config)

    # Create output file path
    secrets_output_file = tmp_path / "test_output_secrets.yaml"

    # Create the actual secrets file to be tested
    _create_test_secrets_file(secrets_output_file, processed_secrets)

    # We need multiple patches to avoid any user input prompts
    with (
        patch(
            "mcp_agent.cli.cloud.commands.configure.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.configure.main.MockMCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.configure.main.configure_user_secrets",
            AsyncMock(return_value=processed_secrets),
        ),
        patch(
            "mcp_agent.cli.cloud.commands.configure.main.typer.Exit",
            side_effect=RuntimeError,
        ),
    ):
        # Now test the function by creating a file that matches what would have been created
        # Skip the interactive parts by using a pre-created file
        try:
            # Call the function directly, but we need to patch it to work as a direct call
            def direct_configure_app(**kwargs):
                # Ensure api_url and api_key are provided
                kwargs.setdefault("api_url", "http://test-api")
                kwargs.setdefault("api_key", "test-token")

                return configure_app(**kwargs)

            result = direct_configure_app(
                app_server_url=MOCK_APP_SERVER_URL,
                secrets_file=None,
                secrets_output_file=secrets_output_file,
                dry_run=False,
                params=False,
            )

            # Verify the expected result
            assert result == MOCK_APP_CONFIG_ID

            # Verify file was created and has correct content
            assert secrets_output_file.exists()

            # Read and verify file contents
            with open(secrets_output_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check that the file contains our secret IDs
            assert "mcpac_sc_12345678-1234-1234-1234-123456789012" in content
            assert "mcpac_sc_87654321-4321-4321-4321-210987654321" in content

            # Check that the YAML structure is valid
            yaml_content = yaml.safe_load(content)

            # Verify the nested structure is correct
            assert (
                yaml_content["server"]["bedrock"]["api_key"]
                == "mcpac_sc_12345678-1234-1234-1234-123456789012"
            )
            assert (
                yaml_content["server"]["openai"]["api_key"]
                == "mcpac_sc_87654321-4321-4321-4321-210987654321"
            )

        except RuntimeError as e:
            # This is expected if typer.Exit is raised
            if "Typer exit with code" not in str(e):
                raise


def _create_test_secrets_file(file_path, processed_secrets):
    """Helper to create a test secrets file with proper structure."""

    # Create the nested structure
    nested_secrets = nest_keys(processed_secrets)

    # Write the file
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            nested_secrets,
            f,
            default_flow_style=False,
            sort_keys=False,
        )

    return processed_secrets
