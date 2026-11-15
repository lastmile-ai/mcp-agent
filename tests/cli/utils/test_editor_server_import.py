import json

import pytest

from mcp_agent.cli.utils.importers import import_servers_from_mcp_json


@pytest.mark.parametrize("key", ["mcpServers", "servers"])
def test_import_editor_server_map(tmp_path, key):
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                key: {
                    "local": {
                        "type": "stdio",
                        "command": "node",
                        "args": ["server.js"],
                        "env": {"MODE": "test"},
                    },
                    "remote": {
                        "type": "http",
                        "url": "https://example.test/mcp",
                        "headers": {"Accept": "application/json"},
                    },
                    "legacy": {
                        "type": "sse",
                        "url": "https://example.test/events",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    servers = import_servers_from_mcp_json(path)

    assert set(servers) == {"local", "remote", "legacy"}
    assert servers["local"].transport == "stdio"
    assert servers["local"].command == "node"
    assert servers["local"].args == ["server.js"]
    assert servers["local"].env == {"MODE": "test"}
    assert servers["remote"].transport == "streamable_http"
    assert servers["remote"].url == "https://example.test/mcp"
    assert servers["remote"].headers == {"Accept": "application/json"}
    assert servers["legacy"].transport == "sse"


@pytest.mark.parametrize(
    "data",
    [
        {"servers": {"command": "node"}},
        {"mcp": {"servers": {"servers": {"command": "node"}}}},
        [{"name": "servers", "command": "node"}],
    ],
    ids=["flat", "nested", "list"],
)
def test_import_existing_formats_with_server_named_servers(tmp_path, data):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    servers = import_servers_from_mcp_json(path)

    assert set(servers) == {"servers"}
    assert servers["servers"].command == "node"
