"""Tests for MCP server URL parsing utilities."""

import pytest
from mcp_agent.cli.utils.url_parser import parse_server_url


@pytest.mark.parametrize(
    "url,expected_transport",
    [
        ("https://example.com/sse", "sse"),
        ("https://example.com/sse/", "sse"),
        ("https://example.com/mcp", "http"),
        ("https://example.com/mcp/", "http"),
    ],
)
def test_parse_server_url_preserves_known_suffixes(url, expected_transport):
    """A trailing slash must not hide the /sse or /mcp suffix."""
    _name, transport, normalized = parse_server_url(url)
    assert transport == expected_transport
    assert normalized == url


def test_parse_server_url_appends_mcp_when_no_suffix():
    _name, transport, normalized = parse_server_url("https://example.com")
    assert transport == "http"
    assert normalized == "https://example.com/mcp"

    _name, transport, normalized = parse_server_url("https://example.com/")
    assert transport == "http"
    assert normalized == "https://example.com/mcp"


def test_parse_server_url_rejects_invalid_urls():
    with pytest.raises(ValueError):
        parse_server_url("")
    with pytest.raises(ValueError):
        parse_server_url("ftp://example.com/sse")
    with pytest.raises(ValueError):
        parse_server_url("http:///sse")
