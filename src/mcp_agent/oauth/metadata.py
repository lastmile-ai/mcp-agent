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


async def fetch_authorization_server_metadata_from_issuer(
    client: httpx.AsyncClient,
    issuer_url: str,
) -> OAuthMetadata:
    """Fetch OAuth authorization server metadata from the well-known endpoint.

    Given an issuer URL, constructs the well-known OAuth authorization server
    metadata URL and fetches the metadata.

    Args:
        client: HTTP client to use for the request
        issuer_url: The issuer URL (e.g., "https://auth.example.com")

    Returns:
        OAuthMetadata containing authorization server metadata including introspection_endpoint
    """
    from httpx import URL

    parsed_url = URL(issuer_url)
    metadata_url = str(
        parsed_url.copy_with(
            path="/.well-known/oauth-authorization-server" + parsed_url.path
        )
    )
    return await fetch_authorization_server_metadata(client, metadata_url)


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
    if resource:
        return resource.rstrip("/")
    if fallback:
        return fallback.rstrip("/")
    raise ValueError("Unable to determine resource identifier for OAuth flow")
