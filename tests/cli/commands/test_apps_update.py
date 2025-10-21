"""Tests for the `mcp-agent apps update` command."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from mcp_agent.cli.cloud.main import app
from mcp_agent.cli.mcp_app.api_client import AppServerInfo, MCPApp, MCPAppConfiguration


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_app(unauthenticated: bool = False) -> MCPApp:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return MCPApp(
        appId="app_12345678-1234-1234-1234-1234567890ab",
        name="Sample App",
        creatorId="u_12345678-1234-1234-1234-1234567890ab",
        description="Initial",
        createdAt=now,
        updatedAt=now,
        appServerInfo=AppServerInfo(
            serverUrl="https://example.com",
            status="APP_SERVER_STATUS_ONLINE",
            unauthenticatedAccess=unauthenticated,
        ),
    )


def test_apps_update_requires_fields(runner: CliRunner):
    result = runner.invoke(
        app,
        [
            "apps",
            "update",
            "app_12345678-1234-1234-1234-1234567890ab",
            "--api-key",
            "token",
        ],
    )

    assert result.exit_code != 0
    assert "Specify at least one" in result.stdout


def test_apps_update_sets_auth_flag(runner: CliRunner):
    existing_app = _make_app()
    updated_app = _make_app(unauthenticated=True)

    mock_client = AsyncMock()
    mock_client.update_app.return_value = updated_app

    with (
        patch(
            "mcp_agent.cli.cloud.commands.apps.update.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.apps.update.main.resolve_server",
            return_value=existing_app,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "apps",
                "update",
                existing_app.appId,
                "--no-auth",
                "--api-key",
                "token",
                "--api-url",
                "http://api",
            ],
        )

    assert result.exit_code == 0, result.stdout
    update_kwargs = mock_client.update_app.await_args.kwargs
    assert update_kwargs["unauthenticated_access"] is True
    assert "Unauthenticated access allowed" in result.stdout


def test_apps_update_accepts_configuration_identifier(runner: CliRunner):
    base_app = _make_app()
    config = MCPAppConfiguration(
        appConfigurationId="apcnf_12345678-1234-1234-1234-1234567890ab",
        app=base_app,
        creatorId="u_12345678-1234-1234-1234-1234567890ab",
    )
    updated_app = _make_app()
    updated_app.description = "Updated description"

    mock_client = AsyncMock()
    mock_client.update_app.return_value = updated_app

    with (
        patch(
            "mcp_agent.cli.cloud.commands.apps.update.main.MCPAppClient",
            return_value=mock_client,
        ),
        patch(
            "mcp_agent.cli.cloud.commands.apps.update.main.resolve_server",
            return_value=config,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "apps",
                "update",
                config.appConfigurationId,
                "--description",
                "Updated description",
                "--api-key",
                "token",
            ],
        )

    assert result.exit_code == 0, result.stdout
    update_kwargs = mock_client.update_app.await_args.kwargs
    assert update_kwargs["description"] == "Updated description"
    assert update_kwargs["app_id"] == base_app.appId
    assert "Description: Updated description" in result.stdout
