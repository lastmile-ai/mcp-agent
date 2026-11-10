import pytest

from mcp_agent.cli.commands.configure import _build_server_entry, _merge_mcp_json
from mcp_agent.cli.utils.url_parser import parse_server_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com?token=value", "https://example.com/mcp?token=value"),
        (
            "https://example.com/api?x=1#section",
            "https://example.com/api/mcp?x=1#section",
        ),
        ("https://example.com/api/", "https://example.com/api/mcp"),
        ("https://example.com/mcp?x=1", "https://example.com/mcp?x=1"),
    ],
)
def test_transport_path_precedes_query_and_fragment(url: str, expected: str) -> None:
    _, transport, normalized = parse_server_url(url)
    assert transport == "http"
    assert normalized == expected


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "192.168.0.1"])
@pytest.mark.parametrize("path", ["", "/api"])
def test_query_distinct_local_servers_survive_config_merge(
    host: str, path: str
) -> None:
    first = _build_server_entry(f"http://{host}:3000{path}?tenant=a")
    second = _build_server_entry(f"http://{host}:3000{path}?tenant=b")
    merged = _merge_mcp_json({"mcp": {"servers": first}}, second)

    assert len(merged["mcp"]["servers"]) == 2
    assert {entry["url"] for entry in merged["mcp"]["servers"].values()} == {
        f"http://{host}:3000{path}/mcp?tenant=a",
        f"http://{host}:3000{path}/mcp?tenant=b",
    }


def test_queryless_local_server_keeps_existing_name() -> None:
    name, _, _ = parse_server_url("http://localhost:3000")
    assert name == "localhost_3000_mcp"
