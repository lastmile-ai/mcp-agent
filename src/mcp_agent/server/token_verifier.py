"""Token verification for MCP Agent Cloud authorization server."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.provider import TokenVerifier

from mcp_agent.config import MCPAuthorizationServerSettings
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.access_token import MCPAccessToken

logger = get_logger(__name__)


class MCPAgentTokenVerifier(TokenVerifier):
    """Verify bearer tokens issued by the MCP Agent Cloud authorization server."""

    def __init__(self, settings: MCPAuthorizationServerSettings):
        if not settings.introspection_endpoint:
            raise ValueError(
                "introspection_endpoint must be configured to verify tokens"
            )
        self._settings = settings
        timeout = httpx.Timeout(10.0)
        self._client = httpx.AsyncClient(timeout=timeout)
        self._cache: Dict[str, MCPAccessToken] = {}
        self._lock = asyncio.Lock()

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
        data = {"token": token}
        auth = None
        if (
            self._settings.introspection_client_id
            and self._settings.introspection_client_secret
        ):
            auth = httpx.BasicAuth(
                self._settings.introspection_client_id,
                self._settings.introspection_client_secret,
            )

        try:
            response = await self._client.post(
                str(self._settings.introspection_endpoint),
                data=data,
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

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MCPAgentTokenVerifier":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
