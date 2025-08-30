"""Tests for the configure command."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_agent.cli.cloud.commands.app.delete.main import delete_app
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppConfiguration
from mcp_agent.cli.mcp_app.mock_client import (
    MOCK_APP_CONFIG_ID,
    MOCK_APP_ID,
    MockMCPAppClient,
)


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP app client."""
    client = MockMCPAppClient()

    mock_config = MagicMock()
    mock_config.appConfigurationId = MOCK_APP_CONFIG_ID
    mock_config.appServerInfo = MagicMock()
    mock_config.appServerInfo.serverUrl = "https://test-server.example.com"
    client.can_delete_app = AsyncMock(return_value=True)
    client.can_delete_app_configuration = AsyncMock(return_value=True)
    client.delete_app = AsyncMock(return_value=True)
    client.delete_app_configuration = AsyncMock(return_value=True)
    return client


@pytest.fixture
def patched_delete_app(mock_mcp_client):
    """Patch the configure_app function for testing."""

    # First, save a reference to the original function
    original_func = delete_app

    # Create a wrapped function that doesn't use typer but has same logic
    def wrapped_delete_app(**kwargs):
        with (
            patch(
                "mcp_agent.cli.cloud.commands.app.delete.main.MCPAppClient",
                return_value=mock_mcp_client,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.app.delete.main.typer.Exit",
                side_effect=ValueError,
            ),
        ):
            try:
                # Call the original function with the provided arguments
                return original_func(**kwargs)
            except ValueError as e:
                # Convert typer.Exit to a test exception with code
                raise RuntimeError(f"Typer exit with code: {e}")

    return wrapped_delete_app


def test_delete_app(patched_delete_app, mock_mcp_client):
    app = MCPApp(
        appId=MOCK_APP_ID,
        name="name",
        creatorId="creatorId",
        createdAt=datetime.datetime.now(),
        updatedAt=datetime.datetime.now(),
    )
    mock_mcp_client.get_app_or_config = AsyncMock(return_value=app)

    # dry run call should not error
    patched_delete_app(
        app_id_or_url=MOCK_APP_ID,
    )

    patched_delete_app(app_id_or_url=MOCK_APP_ID, dry_run=False)
    mock_mcp_client.delete_app.assert_called_once_with(MOCK_APP_ID)


def test_delete_app_config(patched_delete_app, mock_mcp_client):
    app_config = MCPAppConfiguration(
        appConfigurationId=MOCK_APP_CONFIG_ID, creatorId="creator"
    )
    mock_mcp_client.get_app_or_config = AsyncMock(return_value=app_config)

    # dry run call should not error
    patched_delete_app(
        app_id_or_url=MOCK_APP_ID,
    )

    patched_delete_app(app_id_or_url=MOCK_APP_ID, dry_run=False)
    mock_mcp_client.delete_app_configuration.assert_called_once_with(MOCK_APP_CONFIG_ID)


def test_missing_app_id(patched_delete_app):
    """Test with missing app_id."""

    # Test with empty app_id
    with pytest.raises(CLIError):
        patched_delete_app(
            app_id_or_url="",
        )

    # Test with None app_id
    with pytest.raises(CLIError):
        patched_delete_app(
            app_id_or_url=None,
        )


def test_missing_api_key(patched_delete_app):
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
                patched_delete_app(
                    app_id_or_url=MOCK_APP_ID,
                )


def test_invalid_app_id(patched_delete_app):
    with pytest.raises(CLIError):
        patched_delete_app(
            app_id_or_url="foo",
        )
