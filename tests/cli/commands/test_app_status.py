"""Tests for the configure command."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest
from mcp_agent.cli.cloud.commands.app import get_app_status
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppConfiguration, AppServerInfo
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

    return client


@pytest.fixture
def patched_status_app(mock_mcp_client):
    """Patch the configure_app function for testing."""

    # First, save a reference to the original function
    original_func = get_app_status

    # Create a wrapped function that doesn't use typer but has same logic
    def wrapped_status_app(**kwargs):
        with (
            patch(
                "mcp_agent.cli.cloud.commands.app.status.main.MCPAppClient",
                return_value=mock_mcp_client,
            ),
            patch(
                "mcp_agent.cli.cloud.commands.app.status.main.typer.Exit",
                side_effect=ValueError,
            ),
        ):
            try:
                # Call the original function with the provided arguments
                return original_func(**kwargs)
            except ValueError as e:
                # Convert typer.Exit to a test exception with code
                raise RuntimeError(f"Typer exit with code: {e}")

    return wrapped_status_app


def test_status_app(patched_status_app, mock_mcp_client):
    server_url = "https://test-server.example.com"
    app_server_info = AppServerInfo(
        serverUrl=server_url,
        status="APP_SERVER_STATUS_ONLINE",
    )
    app = MCPApp(
        appId=MOCK_APP_ID,
        name="name",
        creatorId="creatorId",
        createdAt=datetime.datetime.now(),
        updatedAt=datetime.datetime.now(),
        appServerInfo=app_server_info,
    )
    mock_mcp_client.get_app_or_config = AsyncMock(return_value=app)

    mock_mcp_print_server_details = Mock()
    with patch(
        "mcp_agent.cli.cloud.commands.app.status.main.print_mcp_server_details",
        side_effect=mock_mcp_print_server_details,
    ) as mocked_function:
        mock_mcp_print_server_details.return_value = None

        patched_status_app(
            app_id_or_url=MOCK_APP_ID,
            api_url=DEFAULT_API_BASE_URL,
            api_key=settings.API_KEY,
        )

        mocked_function.assert_called_once_with(
            server_url=server_url, api_key=settings.API_KEY
        )


def test_status_app_config(patched_status_app, mock_mcp_client):
    server_url = "https://test-server.example.com"
    app_server_info = AppServerInfo(
        serverUrl=server_url,
        status="APP_SERVER_STATUS_ONLINE",
    )
    app_config = MCPAppConfiguration(
        appConfigurationId=MOCK_APP_CONFIG_ID,
        creatorId="creator",
        appServerInfo=app_server_info,
    )
    mock_mcp_client.get_app_or_config = AsyncMock(return_value=app_config)

    mock_mcp_print_server_details = Mock()
    with patch(
        "mcp_agent.cli.cloud.commands.app.status.main.print_mcp_server_details",
        side_effect=mock_mcp_print_server_details,
    ) as mocked_function:
        mock_mcp_print_server_details.return_value = None

        patched_status_app(
            app_id_or_url=MOCK_APP_ID,
            api_url=DEFAULT_API_BASE_URL,
            api_key=settings.API_KEY,
        )

        mocked_function.assert_called_once_with(
            server_url=server_url, api_key=settings.API_KEY
        )


def test_missing_app_id(patched_status_app):
    """Test with missing app_id."""

    # Test with empty app_id
    with pytest.raises(CLIError):
        patched_status_app(
            app_id_or_url="",
        )

    # Test with None app_id
    with pytest.raises(CLIError):
        patched_status_app(
            app_id_or_url=None,
        )


def test_missing_api_key(patched_status_app):
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
                patched_status_app(
                    app_id_or_url=MOCK_APP_ID,
                    api_url=DEFAULT_API_BASE_URL,
                )


def test_invalid_app_id(patched_status_app):
    with pytest.raises(CLIError):
        patched_status_app(
            app_id_or_url="foo",
            api_url=DEFAULT_API_BASE_URL,
        )
