"""Tests for MCP URL SSRF checks (#721)."""

import pytest

from mcp_agent.mcp.url_safety import UnsafeMCPUrlError, validate_mcp_url


def test_rejects_loopback_hostname():
    with pytest.raises(UnsafeMCPUrlError):
        validate_mcp_url("http://localhost:8000/mcp")


def test_rejects_private_literal_ip():
    with pytest.raises(UnsafeMCPUrlError):
        validate_mcp_url("http://127.0.0.1:8000/sse")
    with pytest.raises(UnsafeMCPUrlError):
        validate_mcp_url("http://10.0.0.5/mcp")
    with pytest.raises(UnsafeMCPUrlError):
        validate_mcp_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_bad_scheme():
    with pytest.raises(UnsafeMCPUrlError):
        validate_mcp_url("file:///etc/passwd")


def test_allows_public_https():
    # example.com resolves publicly; if DNS fails, skip.
    try:
        url = validate_mcp_url("https://example.com/mcp")
    except UnsafeMCPUrlError as e:
        if "could not be resolved" in str(e):
            pytest.skip("DNS unavailable")
        raise
    assert url == "https://example.com/mcp"


def test_allow_private_opt_in():
    assert validate_mcp_url("http://127.0.0.1:9/mcp", allow_private=True).startswith(
        "http://127.0.0.1"
    )
