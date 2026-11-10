import pytest

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
