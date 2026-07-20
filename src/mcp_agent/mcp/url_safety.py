"""URL safety checks for MCP network transports (SSRF mitigation)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeMCPUrlError(ValueError):
    """Raised when an MCP server URL targets a non-public or disallowed host."""


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    }
)


def _is_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def validate_mcp_url(url: str, *, allow_private: bool = False) -> str:
    """Validate that *url* is safe to open as an MCP network transport.

    Blocks loopback, private, link-local, and cloud-metadata ranges by default
    so untrusted MCP configs cannot SSRF into the local network (#721).

    Args:
        url: Absolute http(s)/ws(s) URL from server configuration.
        allow_private: If True, skip private-range checks (local/dev only).

    Returns:
        The original URL when validation passes.

    Raises:
        UnsafeMCPUrlError: If the scheme/host is disallowed or resolves to a
            non-public address.
    """
    if not url or not isinstance(url, str):
        raise UnsafeMCPUrlError("MCP server URL must be a non-empty string")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https", "ws", "wss"}:
        raise UnsafeMCPUrlError(
            f"Unsupported MCP URL scheme {scheme!r}; expected http(s) or ws(s)"
        )

    host = parsed.hostname
    if not host:
        raise UnsafeMCPUrlError("MCP server URL must include a hostname")

    host_l = host.lower().rstrip(".")
    if host_l in _BLOCKED_HOSTNAMES or host_l.endswith(".localhost"):
        if not allow_private:
            raise UnsafeMCPUrlError(
                f"MCP server URL host {host!r} is not allowed (loopback/metadata)"
            )

    # Literal IP in the URL
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if not allow_private and _is_non_public_ip(ip):
            raise UnsafeMCPUrlError(
                f"MCP server URL must not target non-public IP {ip}"
            )
        return url

    # Resolve hostname and check every address
    if not allow_private:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 0, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeMCPUrlError(
                f"MCP server URL host {host!r} could not be resolved: {exc}"
            ) from exc
        for info in infos:
            addr = info[4][0]
            try:
                resolved = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if _is_non_public_ip(resolved):
                raise UnsafeMCPUrlError(
                    f"MCP server URL host {host!r} resolves to non-public "
                    f"address {resolved}"
                )

    return url
