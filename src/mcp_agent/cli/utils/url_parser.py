"""
Utilities to parse MCP server URLs and generate config entries.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Literal, Tuple
from urllib.parse import urlparse


def parse_server_url(url: str) -> Tuple[str, Literal["http", "sse"], str]:
    """
    Parse a server URL and determine the transport type and normalized URL.

    Returns (server_name, transport_type, normalized_url)
    """
    if not url:
        raise ValueError("URL cannot be empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must be http/https: {url}")
    if not parsed.netloc:
        raise ValueError(f"URL must include a hostname: {url}")

    transport: Literal["http", "sse"] = "http"
    if parsed.path.endswith("/sse"):
        transport = "sse"
        normalized = url
    elif parsed.path.endswith("/mcp"):
        normalized = url
    else:
        base = url if url.endswith("/") else f"{url}/"
        normalized = f"{base}mcp"

    name = generate_server_name(normalized)
    return name, transport, normalized


def generate_server_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.split(":")[0]
    clean = re.sub(r"[^a-zA-Z0-9]", "_", host)
    if len(clean) > 15:
        clean = clean[:9] + clean[-5:]
    if clean in ("localhost", "127_0_0_1") or re.match(r"^(\d+_){3}\d+$", clean):
        path = parsed.path.strip("/")
        path = re.sub(r"[^a-zA-Z0-9]", "_", path)
        port = ""
        if ":" in parsed.netloc:
            port = f"_{parsed.netloc.split(':')[1]}"
        if path:
            return f"{clean}{port}_{path[:20]}"
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{clean}{port}_{url_hash}"
    return clean


def parse_server_urls(
    urls_param: str, auth_token: str | None = None
) -> List[Tuple[str, Literal["http", "sse"], str, Dict[str, str] | None]]:
    if not urls_param:
        return []
    url_list = [u.strip() for u in urls_param.split(",") if u.strip()]
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
    result = []
    for raw in url_list:
        name, transport, normalized = parse_server_url(raw)
        result.append((name, transport, normalized, headers))
    return result


def generate_server_configs(
    parsed_urls: List[Tuple[str, Literal["http", "sse"], str, Dict[str, str] | None]],
) -> Dict[str, Dict[str, str | Dict[str, str]]]:
    configs: Dict[str, Dict[str, str | Dict[str, str]]] = {}
    name_counts: Dict[str, int] = {}
    for name, transport, url, headers in parsed_urls:
        final = name
        if final in configs:
            cnt = name_counts.get(name, 1)
            final = f"{name}_{cnt}"
            name_counts[name] = cnt + 1
            while final in configs:
                cnt = name_counts.get(name, 1)
                final = f"{name}_{cnt}"
                name_counts[name] = cnt + 1
        cfg: Dict[str, str | Dict[str, str]] = {"transport": transport, "url": url}
        if headers:
            cfg["headers"] = headers
        configs[final] = cfg
    return configs
