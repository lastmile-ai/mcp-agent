"""Helpers for OAuth metadata discovery."""

from __future__ import annotations

from typing import List

import httpx
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
    candidates: List[str] = list(metadata.authorization_servers or [])
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
    if resource:
        return resource.rstrip("/")
    if fallback:
        return fallback.rstrip("/")
    raise ValueError("Unable to determine resource identifier for OAuth flow")
