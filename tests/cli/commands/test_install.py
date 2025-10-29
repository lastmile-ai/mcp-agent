"""Tests for the install command."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_agent.cli.commands.install import (
    _build_server_config,
    _merge_mcp_json,
    install,
)
from mcp_agent.cli.exceptions import CLIError


MOCK_APP_SERVER_URL = "https://test-server.example.com/sse"


@pytest.fixture
def mock_app_with_auth():
    """Create a mock app that requires authentication."""
    app = MagicMock()
    app.appId = "app-123"
    app.name = "test-app"
    app.unauthenticatedAccess = False
    app.appServerInfo = MagicMock()
    app.appServerInfo.serverUrl = MOCK_APP_SERVER_URL
    app.appServerInfo.unauthenticatedAccess = False
    return app


@pytest.fixture
def mock_app_without_auth():
    """Create a mock app with unauthenticated access."""
    app = MagicMock()
    app.appId = "app-456"
    app.name = "test-app-public"
    app.unauthenticatedAccess = True
    app.appServerInfo = MagicMock()
    app.appServerInfo.serverUrl = MOCK_APP_SERVER_URL
    app.appServerInfo.unauthenticatedAccess = True
    return app


def test_build_server_config():
    """Test server configuration building with auth header."""
    config = _build_server_config("https://example.com/mcp", "http", api_key="test-key")
    assert config == {
        "url": "https://example.com/mcp",
        "transport": "http",
        "headers": {"Authorization": "Bearer test-key"},
    }

    config_sse = _build_server_config(
        "https://example.com/sse", "sse", api_key="test-key"
    )
    assert config_sse == {
        "url": "https://example.com/sse",
        "transport": "sse",
        "headers": {"Authorization": "Bearer test-key"},
    }

    # Claude Desktop uses mcp-remote wrapper with actual API key
    config_claude = _build_server_config(
        "https://example.com/sse",
        "sse",
        for_claude_desktop=True,
        api_key="test-api-key-123",
    )
    assert config_claude == {
        "command": "npx",
        "args": [
            "mcp-remote",
            "https://example.com/sse",
            "--header",
            "Authorization: Bearer test-api-key-123",
        ],
    }


def test_merge_mcp_json_empty():
    """Test merging into empty config."""
    result = _merge_mcp_json(
        {},
        "test-server",
        {
            "url": "https://example.com",
            "transport": "http",
            "headers": {"Authorization": "Bearer test-key"},
        },
    )
    assert result == {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://example.com",
                    "transport": "http",
                    "headers": {"Authorization": "Bearer test-key"},
                }
            }
        }
    }


def test_merge_mcp_json_claude_format():
    """Test merging with Claude Desktop format."""
    result = _merge_mcp_json(
        {},
        "test-server",
        {"command": "npx", "args": ["mcp-remote", "https://example.com/sse"]},
        format_type="mcpServers",
    )
    assert result == {
        "mcpServers": {
            "test-server": {
                "command": "npx",
                "args": ["mcp-remote", "https://example.com/sse"],
            }
        }
    }


def test_merge_mcp_json_vscode_format():
    """Test merging with VSCode format."""
    result = _merge_mcp_json(
        {},
        "test-server",
        {
            "type": "sse",
            "url": "https://example.com",
            "headers": {"Authorization": "Bearer test-key"},
        },
        format_type="vscode",
    )
    assert result == {
        "servers": {
            "test-server": {
                "type": "sse",
                "url": "https://example.com",
                "headers": {"Authorization": "Bearer test-key"},
            }
        },
        "inputs": [],
    }


def test_merge_mcp_json_existing():
    """Test merging into existing config."""
    existing = {
        "mcp": {
            "servers": {
                "existing-server": {
                    "url": "https://existing.com",
                    "transport": "http",
                }
            }
        }
    }
    result = _merge_mcp_json(
        existing,
        "new-server",
        {
            "url": "https://new.com",
            "transport": "http",
            "headers": {"Authorization": "Bearer test-key"},
        },
    )
    assert result == {
        "mcp": {
            "servers": {
                "existing-server": {
                    "url": "https://existing.com",
                    "transport": "http",
                },
                "new-server": {
                    "url": "https://new.com",
                    "transport": "http",
                    "headers": {"Authorization": "Bearer test-key"},
                },
            }
        }
    }


def test_merge_mcp_json_overwrite():
    """Test overwriting existing server."""
    existing = {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://old.com",
                    "transport": "http",
                }
            }
        }
    }
    result = _merge_mcp_json(
        existing,
        "test-server",
        {
            "url": "https://new.com",
            "transport": "sse",
            "headers": {"Authorization": "Bearer test-key"},
        },
    )
    assert result == {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://new.com",
                    "transport": "sse",
                    "headers": {"Authorization": "Bearer test-key"},
                }
            }
        }
    }


def test_install_missing_api_key(tmp_path):
    """Test install fails without API key."""
    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials", return_value=None
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = None
            mock_settings.API_BASE_URL = "http://test-api"

            with pytest.raises(CLIError, match="Must be logged in"):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name=None,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_invalid_client():
    """Test install fails with invalid client."""
    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with pytest.raises(CLIError, match="Unsupported client"):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="invalid-client",
                    name=None,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_invalid_url():
    """Test install fails with non-URL identifier."""
    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with pytest.raises(CLIError, match="must be a URL"):
                install(
                    server_identifier="not-a-url",
                    client="vscode",
                    name=None,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_vscode(tmp_path):
    """Test install to VSCode."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name="test-server",
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                # Verify config file was created
                assert vscode_config.exists()

                # Verify config contents (VSCode format)
                config = json.loads(vscode_config.read_text())
                assert "servers" in config
                assert "inputs" in config
                assert "test-server" in config["servers"]
                server = config["servers"]["test-server"]
                assert server["url"] == MOCK_APP_SERVER_URL
                assert server["type"] == "sse"
                assert server["headers"]["Authorization"] == "Bearer test-key"


def test_install_cursor_with_existing_config(tmp_path):
    """Test install to Cursor with existing configuration."""
    cursor_config = tmp_path / ".cursor" / "mcp.json"
    cursor_config.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        "mcpServers": {
            "existing-server": {
                "url": "https://existing.com/mcp",
                "transport": "http",
            }
        }
    }
    cursor_config.write_text(json.dumps(existing, indent=2))

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.home", return_value=tmp_path
            ):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="cursor",
                    name="new-server",
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                config = json.loads(cursor_config.read_text())
                assert len(config["mcpServers"]) == 2
                assert "existing-server" in config["mcpServers"]
                assert "new-server" in config["mcpServers"]


def test_install_duplicate_without_force(tmp_path):
    """Test install fails when server already exists without --force."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"
    vscode_config.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        "servers": {
            "test-server": {
                "url": "https://old.com/mcp",
                "type": "http",
            }
        },
        "inputs": [],
    }
    vscode_config.write_text(json.dumps(existing, indent=2))

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                with pytest.raises(CLIError, match="already exists"):
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="vscode",
                        name="test-server",
                        dry_run=False,
                        force=False,
                        api_url="http://test-api",
                        api_key="test-key",
                    )


def test_install_duplicate_with_force(tmp_path):
    """Test install overwrites when server exists with --force."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"
    vscode_config.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        "servers": {
            "test-server": {
                "url": "https://old.com/mcp",
                "type": "http",
            }
        },
        "inputs": [],
    }
    vscode_config.write_text(json.dumps(existing, indent=2))

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name="test-server",
                    dry_run=False,
                    force=True,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                config = json.loads(vscode_config.read_text())
                assert config["servers"]["test-server"]["url"] == MOCK_APP_SERVER_URL


def test_install_chatgpt_requires_unauth_access(mock_app_with_auth):
    """Test ChatGPT install fails when server requires authentication."""
    import typer

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.get_app = AsyncMock(return_value=mock_app_with_auth)
                mock_client_class.return_value = mock_client

                with pytest.raises(typer.Exit) as exc_info:
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="chatgpt",
                        name=None,
                        dry_run=False,
                        force=False,
                        api_url="http://test-api",
                        api_key="test-key",
                    )

                assert exc_info.value.exit_code == 1


def test_install_chatgpt_with_unauth_server(mock_app_without_auth):
    """Test ChatGPT install succeeds with unauthenticated server."""
    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.get_app = AsyncMock(return_value=mock_app_without_auth)
                mock_client_class.return_value = mock_client

                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="chatgpt",
                    name=None,
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )


def test_install_dry_run(tmp_path, capsys):
    """Test install in dry run mode."""
    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name="test-server",
                    dry_run=True,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                vscode_config = tmp_path / ".vscode" / "mcp.json"
                assert not vscode_config.exists()


def test_install_sse_transport_detection(tmp_path):
    """Test that SSE transport is detected from URL."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                install(
                    server_identifier="https://example.com/sse",
                    client="vscode",
                    name="test-server",
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                config = json.loads(vscode_config.read_text())
                assert config["servers"]["test-server"]["type"] == "sse"


def test_install_http_transport_detection(tmp_path):
    """Test that HTTP transport is detected from URL."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"

    with patch(
        "mcp_agent.cli.commands.install.load_api_key_credentials",
        return_value="test-key",
    ):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with patch(
                "mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path
            ):
                install(
                    server_identifier="https://example.com/mcp",
                    client="vscode",
                    name="test-server",
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                config = json.loads(vscode_config.read_text())
                assert config["servers"]["test-server"]["type"] == "http"
