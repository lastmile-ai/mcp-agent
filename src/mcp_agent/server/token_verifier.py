"""Token verification for MCP Agent Cloud authorization server."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from httpx import URL

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.provider import TokenVerifier

from mcp_agent.config import MCPAuthorizationServerSettings
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.access_token import MCPAccessToken

logger = get_logger(__name__)


class MCPAgentTokenVerifier(TokenVerifier):
    """Verify bearer tokens issued by the MCP Agent Cloud authorization server."""

    def __init__(self, settings: MCPAuthorizationServerSettings):
        self._settings = settings
        timeout = httpx.Timeout(10.0)
        self._client = httpx.AsyncClient(timeout=timeout)
        self._cache: Dict[str, MCPAccessToken] = {}
        self._lock = asyncio.Lock()
        self._introspection_endpoint: str | None = None
        self._metadata_fetch_lock = asyncio.Lock()

    async def _ensure_introspection_endpoint(self) -> str:
        """Ensure introspection endpoint is available, fetching from well-known if needed."""
        # Check if already fetched
        if self._introspection_endpoint:
            return self._introspection_endpoint

        # Fetch from well-known endpoint
        async with self._metadata_fetch_lock:
            # Double-check after acquiring lock
            if self._introspection_endpoint:
                return self._introspection_endpoint

            if not self._settings.issuer_url:
                raise ValueError(
                    "issuer_url must be configured to fetch introspection endpoint"
                )

            try:
                from mcp_agent.oauth.metadata import (
                    fetch_authorization_server_metadata,
                )

                parsed_url = URL(str(self._settings.issuer_url))
                metadata_url = str(
                    parsed_url.copy_with(
                        path="/.well-known/oauth-authorization-server" + parsed_url.path
                    )
                )

                # Pydantics AnyHttpUrl may add a trailing `/`, remove it
                if metadata_url.endswith("/"):
                    metadata_url = metadata_url[:-1]

                metadata = await fetch_authorization_server_metadata(
                    self._client, str(metadata_url)
                )

                if not metadata.introspection_endpoint:
                    raise ValueError(
                        f"Authorization server at {self._settings.issuer_url} does not "
                        "advertise an introspection endpoint in its metadata"
                    )

                self._introspection_endpoint = str(metadata.introspection_endpoint)
                logger.info(
                    "Fetched introspection endpoint from authorization server metadata",
                    data={"introspection_endpoint": self._introspection_endpoint},
                )
                return self._introspection_endpoint

            except Exception as exc:
                logger.error(
                    "Failed to fetch authorization server metadata",
                    data={"issuer_url": str(self._settings.issuer_url)},
                    exc_info=True,
                )
                raise ValueError(
                    f"Failed to fetch introspection endpoint from {self._settings.issuer_url}: {exc}"
                ) from exc

    async def verify_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        cached = self._cache.get(token)
        if cached and not cached.is_expired(leeway_seconds=30):
            return cached

        async with self._lock:
            # Double-check cache after acquiring lock to avoid duplicate refresh
            cached = self._cache.get(token)
            if cached and not cached.is_expired(leeway_seconds=30):
                return cached

            verified = await self._introspect(token)
            if verified:
                self._cache[token] = verified
            else:
                self._cache.pop(token, None)

            return verified

    async def _introspect(self, token: str) -> MCPAccessToken | None:
        # Ensure we have the introspection endpoint
        try:
            introspection_endpoint = await self._ensure_introspection_endpoint()
        except ValueError as exc:
            logger.error(f"Cannot introspect token: {exc}")
            return None

        data = {"token": token}

        auth = None
        if self._settings.client_id and self._settings.client_secret:
            auth = httpx.BasicAuth(
                self._settings.client_id,
                self._settings.client_secret,
            )

        try:
            response = await self._client.post(
                introspection_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=auth,
            )
        except httpx.HTTPError as exc:
            logger.warning(f"Token introspection request failed: {exc}")
            return None

        if response.status_code != 200:
            logger.warning(
                "Token introspection returned non-success status",
                data={"status_code": response.status_code},
            )
            return None

        try:
            payload: Dict[str, Any] = response.json()
        except ValueError:
            logger.warning("Token introspection response was not valid JSON")
            return None

        if not payload.get("active"):
            return None

        if self._settings.issuer_url and payload.get("iss"):
            if str(payload.get("iss")) != str(self._settings.issuer_url):
                logger.warning(
                    "Token issuer mismatch",
                    data={
                        "expected": str(self._settings.issuer_url),
                        "actual": payload.get("iss"),
                    },
                )
                return None

        # RFC 9068 Audience Validation (always enforced)
        token_audiences = self._extract_audiences(payload)
        if not self._validate_audiences(token_audiences):
            logger.warning(
                "Token audience validation failed",
                data={
                    "token_audiences": token_audiences,
                    "expected_audiences": self._settings.expected_audiences,
                },
            )
            return None

        token_model = MCPAccessToken.from_introspection(
            token,
            payload,
            resource_hint=str(self._settings.resource_server_url)
            if self._settings.resource_server_url
            else None,
        )

        # Respect cache TTL limit if configured
        ttl_seconds = max(0, self._settings.token_cache_ttl_seconds or 0)
        if ttl_seconds and token_model.expires_at is not None:
            now_ts = datetime.now(tz=timezone.utc).timestamp()
            cache_limit = now_ts + ttl_seconds
            token_model.expires_at = min(token_model.expires_at, cache_limit)

        # Optionally enforce required scopes
        required_scopes = self._settings.required_scopes or []
        missing = [
            scope for scope in required_scopes if scope not in token_model.scopes
        ]
        if missing:
            logger.warning(
                "Token missing required scopes",
                data={"missing_scopes": missing},
            )
            return None

        return token_model

    def _extract_audiences(self, payload: Dict[str, Any]) -> List[str]:
        """Extract audience values from token payload according to RFC 9068."""
        audiences = []

        # Check both 'aud' and 'resource' claims (OAuth 2.0 resource indicators)
        aud_claim = payload.get("aud")
        resource_claim = payload.get("resource")

        # Handle 'aud' claim (can be string or array)
        if aud_claim:
            if isinstance(aud_claim, str):
                audiences.append(aud_claim)
            elif isinstance(aud_claim, (list, tuple)):
                audiences.extend([str(aud) for aud in aud_claim if aud])

        # Handle 'resource' claim (OAuth 2.0 resource indicator)
        if resource_claim:
            if isinstance(resource_claim, str):
                audiences.append(resource_claim)
            elif isinstance(resource_claim, (list, tuple)):
                audiences.extend([str(res) for res in resource_claim if res])

        return list(set(audiences))  # Remove duplicates

    def _validate_audiences(self, token_audiences: List[str]) -> bool:
        """Validate token audiences against expected values per RFC 9068."""
        if not token_audiences:
            logger.warning("Token contains no audience claims")
            return False

        if not self._settings.expected_audiences:
            logger.warning("No expected audiences configured for validation")
            return False

        # RFC 9068: Token MUST contain at least one expected audience
        valid_audiences = set(self._settings.expected_audiences)
        token_audience_set = set(token_audiences)

        if not valid_audiences.intersection(token_audience_set):
            logger.warning(
                "Token audience validation failed - no matching audiences",
                data={
                    "token_audiences": list(token_audience_set),
                    "valid_audiences": list(valid_audiences),
                },
            )
            return False

        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MCPAgentTokenVerifier":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
