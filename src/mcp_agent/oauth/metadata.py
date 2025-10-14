"""Helpers for OAuth metadata discovery."""

from __future__ import annotations

from typing import List

import httpx
from httpx import URL
from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


async def fetch_resource_metadata(
    client: httpx.AsyncClient,
    resource_metadata_url: str,
) -> ProtectedResourceMetadata:
    response = await client.get(resource_metadata_url)
    response.raise_for_status()
    data = response.json()
    return ProtectedResourceMetadata.model_validate(data)


async def fetch_authorization_server_metadata(
    client: httpx.AsyncClient,
    metadata_url: str,
) -> OAuthMetadata:
    response = await client.get(metadata_url)
    response.raise_for_status()
    return OAuthMetadata.model_validate(response.json())


def select_authorization_server(
    metadata: ProtectedResourceMetadata,
    preferred: str | None = None,
) -> str:
    candidates: List[str] = [str(url) for url in (metadata.authorization_servers or [])]
    if not candidates:
        raise ValueError(
            "Protected resource metadata did not include authorization servers"
        )

    if preferred and preferred in candidates:
        return preferred

    if preferred:
        logger.warning(
            "Preferred authorization server not listed; falling back to first entry",
            data={"preferred": preferred, "candidates": candidates},
        )
    return candidates[0]


def normalize_resource(resource: str | None, fallback: str | None) -> str:
    candidate = resource or fallback
    if not candidate:
        raise ValueError("Unable to determine resource identifier for OAuth flow")

    parsed = URL(candidate)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported resource scheme: {parsed.scheme}")

    host = parsed.host.lower() if parsed.host else parsed.host
    path = parsed.path.rstrip("/")
    if path == "/":
        path = ""
    canonical = parsed.copy_with(
        scheme=parsed.scheme,
        host=host,
        path=path,
        query=None,
        fragment=None,
    )
    return str(canonical)
