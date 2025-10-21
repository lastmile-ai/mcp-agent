"""Tests for the install command."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_agent.cli.commands.install import (
    _build_server_config,
    _generate_server_name,
    _merge_mcp_json,
    install,
)
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.mock_client import (
    MOCK_APP_CONFIG_ID,
    MOCK_APP_ID,
    MOCK_APP_SERVER_URL,
)


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
    mock_config.appServerInfo.serverUrl = "https://test-server.example.com/mcp"
    client.configure_app = AsyncMock(return_value=mock_config)

    return client


def test_generate_server_name():
    """Test server name generation from URLs."""
    assert _generate_server_name("https://api.example.com/servers/my-server/mcp") == "my-server"
    assert _generate_server_name("https://api.example.com/mcp") == "api.example.com"
    assert _generate_server_name("https://example.com") == "example.com"


def test_build_server_config():
    """Test server configuration building."""
    config = _build_server_config("https://example.com/mcp", "http")
    assert config == {
        "url": "https://example.com/mcp",
        "transport": "http",
    }

    config_sse = _build_server_config("https://example.com/sse", "sse")
    assert config_sse == {
        "url": "https://example.com/sse",
        "transport": "sse",
    }


def test_merge_mcp_json_empty():
    """Test merging into empty config."""
    result = _merge_mcp_json({}, "test-server", {"url": "https://example.com", "transport": "http"})
    assert result == {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://example.com",
                    "transport": "http",
                }
            }
        }
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
        {"url": "https://new.com", "transport": "http"},
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
        {"url": "https://new.com", "transport": "sse"},
    )
    assert result == {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://new.com",
                    "transport": "sse",
                }
            }
        }
    }


def test_install_missing_api_key(tmp_path):
    """Test install fails without API key."""
    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value=None):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = None
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with pytest.raises(CLIError, match="Must be logged in"):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name=None,
                    secrets_file=None,
                    secrets_output_file=None,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_invalid_client():
    """Test install fails with invalid client."""
    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            with pytest.raises(CLIError, match="Unsupported client"):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="invalid-client",
                    name=None,
                    secrets_file=None,
                    secrets_output_file=None,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_both_secrets_files():
    """Test install fails with both secrets file options."""
    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"

            secrets_file = Path("/tmp/secrets.yaml")
            secrets_output_file = Path("/tmp/output.yaml")

            with pytest.raises(CLIError, match="Cannot provide both"):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name=None,
                    secrets_file=secrets_file,
                    secrets_output_file=secrets_output_file,
                    dry_run=False,
                    force=False,
                    api_url=None,
                    api_key=None,
                )


def test_install_dry_run(mock_mcp_client, tmp_path, capsys):
    """Test install in dry run mode."""
    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MockMCPAppClient",
                return_value=mock_mcp_client,
            ):
                # No exception should be raised
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="vscode",
                    name="test-server",
                    secrets_file=None,
                    secrets_output_file=None,
                    dry_run=True,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                # Verify configure_app was not called in dry run
                mock_mcp_client.configure_app.assert_not_called()


def test_install_vscode_no_secrets(mock_mcp_client, tmp_path):
    """Test install to VSCode without secrets."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch("mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path):
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="vscode",
                        name="test-server",
                        secrets_file=None,
                        secrets_output_file=None,
                        dry_run=False,
                        force=False,
                        api_url="http://test-api",
                        api_key="test-key",
                    )

                    # Verify config file was created
                    assert vscode_config.exists()

                    # Verify config contents
                    config = json.loads(vscode_config.read_text())
                    assert "mcp" in config
                    assert "servers" in config["mcp"]
                    assert "test-server" in config["mcp"]["servers"]
                    assert config["mcp"]["servers"]["test-server"]["url"] == "https://test-server.example.com/mcp"
                    assert config["mcp"]["servers"]["test-server"]["transport"] == "http"


def test_install_cursor_with_existing_config(mock_mcp_client, tmp_path):
    """Test install to Cursor with existing configuration."""
    cursor_config = tmp_path / ".cursor" / "mcp.json"
    cursor_config.parent.mkdir(parents=True, exist_ok=True)

    # Create existing config
    existing = {
        "mcp": {
            "servers": {
                "existing-server": {
                    "url": "https://existing.com/mcp",
                    "transport": "http",
                }
            }
        }
    }
    cursor_config.write_text(json.dumps(existing, indent=2))

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch("mcp_agent.cli.commands.install.Path.home", return_value=tmp_path):
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="cursor",
                        name="new-server",
                        secrets_file=None,
                        secrets_output_file=None,
                        dry_run=False,
                        force=False,
                        api_url="http://test-api",
                        api_key="test-key",
                    )

                    # Verify config file was updated
                    config = json.loads(cursor_config.read_text())
                    assert len(config["mcp"]["servers"]) == 2
                    assert "existing-server" in config["mcp"]["servers"]
                    assert "new-server" in config["mcp"]["servers"]


def test_install_duplicate_without_force(mock_mcp_client, tmp_path):
    """Test install fails when server already exists without --force."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"
    vscode_config.parent.mkdir(parents=True, exist_ok=True)

    # Create existing config with same server name
    existing = {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://old.com/mcp",
                    "transport": "http",
                }
            }
        }
    }
    vscode_config.write_text(json.dumps(existing, indent=2))

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch("mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path):
                    with pytest.raises(CLIError, match="already exists"):
                        install(
                            server_identifier=MOCK_APP_SERVER_URL,
                            client="vscode",
                            name="test-server",
                            secrets_file=None,
                            secrets_output_file=None,
                            dry_run=False,
                            force=False,
                            api_url="http://test-api",
                            api_key="test-key",
                        )


def test_install_duplicate_with_force(mock_mcp_client, tmp_path):
    """Test install overwrites when server exists with --force."""
    vscode_config = tmp_path / ".vscode" / "mcp.json"
    vscode_config.parent.mkdir(parents=True, exist_ok=True)

    # Create existing config with same server name
    existing = {
        "mcp": {
            "servers": {
                "test-server": {
                    "url": "https://old.com/mcp",
                    "transport": "http",
                }
            }
        }
    }
    vscode_config.write_text(json.dumps(existing, indent=2))

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch("mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path):
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="vscode",
                        name="test-server",
                        secrets_file=None,
                        secrets_output_file=None,
                        dry_run=False,
                        force=True,
                        api_url="http://test-api",
                        api_key="test-key",
                    )

                    # Verify config was updated
                    config = json.loads(vscode_config.read_text())
                    assert config["mcp"]["servers"]["test-server"]["url"] == "https://test-server.example.com/mcp"


def test_install_chatgpt_prints_instructions(mock_mcp_client, capsys):
    """Test install to ChatGPT prints instructions instead of writing config."""
    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                install(
                    server_identifier=MOCK_APP_SERVER_URL,
                    client="chatgpt",
                    name="test-server",
                    secrets_file=None,
                    secrets_output_file=None,
                    dry_run=False,
                    force=False,
                    api_url="http://test-api",
                    api_key="test-key",
                )

                # Verify configure_app was called
                mock_mcp_client.configure_app.assert_called_once()


def test_install_with_secrets(mock_mcp_client, tmp_path):
    """Test install with required secrets."""
    # Mock client to require secrets
    mock_mcp_client.list_config_params = AsyncMock(
        return_value=["server.api_key", "server.secret"]
    )

    vscode_config = tmp_path / ".vscode" / "mcp.json"
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("server:\n  api_key: test-key\n  secret: test-secret\n")

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch(
                    "mcp_agent.cli.commands.install.configure_user_secrets",
                    AsyncMock(return_value={"server.api_key": "id1", "server.secret": "id2"}),
                ):
                    with patch("mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path):
                        install(
                            server_identifier=MOCK_APP_SERVER_URL,
                            client="vscode",
                            name="test-server",
                            secrets_file=secrets_file,
                            secrets_output_file=None,
                            dry_run=False,
                            force=False,
                            api_url="http://test-api",
                            api_key="test-key",
                        )

                        # Verify config file was created
                        assert vscode_config.exists()

                        # Verify configure_app was called with secrets
                        mock_mcp_client.configure_app.assert_called_once()


def test_install_sse_transport_detection(mock_mcp_client, tmp_path):
    """Test that SSE transport is detected from URL."""
    # Mock to return SSE URL
    mock_config = MagicMock()
    mock_config.appConfigurationId = MOCK_APP_CONFIG_ID
    mock_config.appServerInfo = MagicMock()
    mock_config.appServerInfo.serverUrl = "https://test-server.example.com/sse"
    mock_mcp_client.configure_app = AsyncMock(return_value=mock_config)

    vscode_config = tmp_path / ".vscode" / "mcp.json"

    with patch("mcp_agent.cli.commands.install.load_api_key_credentials", return_value="test-key"):
        with patch("mcp_agent.cli.commands.install.settings") as mock_settings:
            mock_settings.API_KEY = "test-key"
            mock_settings.API_BASE_URL = "http://test-api"
            mock_settings.VERBOSE = False

            with patch(
                "mcp_agent.cli.commands.install.MCPAppClient",
                return_value=mock_mcp_client,
            ):
                with patch("mcp_agent.cli.commands.install.Path.cwd", return_value=tmp_path):
                    install(
                        server_identifier=MOCK_APP_SERVER_URL,
                        client="vscode",
                        name="test-server",
                        secrets_file=None,
                        secrets_output_file=None,
                        dry_run=False,
                        force=False,
                        api_url="http://test-api",
                        api_key="test-key",
                    )

                    # Verify SSE transport was used
                    config = json.loads(vscode_config.read_text())
                    assert config["mcp"]["servers"]["test-server"]["transport"] == "sse"
