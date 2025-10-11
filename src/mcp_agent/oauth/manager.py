"""Token management for downstream OAuth-protected MCP servers."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Dict, Iterable, Sequence, TYPE_CHECKING

import httpx
from httpx import URL

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.errors import (
    OAuthFlowError,
    TokenRefreshError,
)
from mcp_agent.oauth.flow import AuthorizationFlowCoordinator
from mcp_agent.oauth.identity import OAuthUserIdentity
from mcp_agent.oauth.metadata import (
    fetch_authorization_server_metadata,
    fetch_resource_metadata,
    normalize_resource,
    select_authorization_server,
)
from mcp_agent.oauth.records import TokenRecord
from mcp_agent.oauth.store import (
    InMemoryTokenStore,
    TokenStore,
    TokenStoreKey,
    scope_fingerprint,
)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


def create_default_user_for_preconfigured_tokens(
    session_id: str | None = None,
) -> "OAuthUserIdentity":
    """Create a synthetic user identity for pre-configured tokens."""
    from mcp_agent.oauth.identity import OAuthUserIdentity

    return OAuthUserIdentity(
        provider="mcp-agent",
        subject=f"preconfigured-tokens-{session_id}"
        if session_id
        else "preconfigured-tokens",
        claims={
            "token_source": "preconfigured",
            "description": "Synthetic user for pre-configured OAuth tokens",
        },
    )


class TokenManager:
    """High-level orchestrator for acquiring and refreshing OAuth tokens."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        token_store: TokenStore | None = None,
        settings: OAuthSettings | None = None,
    ) -> None:
        self._settings = settings or OAuthSettings()
        self._token_store = token_store or InMemoryTokenStore()
        self._http_client = http_client or httpx.AsyncClient(timeout=30.0)
        self._own_http_client = http_client is None
        self._flow = AuthorizationFlowCoordinator(
            http_client=self._http_client, settings=self._settings
        )
        self._locks: Dict[TokenStoreKey, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._resource_metadata_cache: Dict[str, tuple[float, object]] = {}
        self._auth_metadata_cache: Dict[str, tuple[float, object]] = {}

    async def store_preconfigured_token(
        self, server_name: str, server_config, synthetic_user: "OAuthUserIdentity"
    ) -> None:
        """Store a pre-configured token in the token store."""
        oauth_config = server_config.auth.oauth

        # Create token record
        resource_str = (
            str(oauth_config.resource)
            if oauth_config.resource
            else getattr(server_config, "url", None)
        )
        auth_server_str = (
            str(oauth_config.authorization_server)
            if oauth_config.authorization_server
            else None
        )

        from datetime import datetime, timezone

        record = TokenRecord(
            access_token=oauth_config.access_token,
            refresh_token=oauth_config.refresh_token,
            scopes=tuple(oauth_config.scopes or []),
            expires_at=oauth_config.expires_at,
            token_type=oauth_config.token_type,
            resource=resource_str,
            authorization_server=auth_server_str,
            obtained_at=datetime.now(tz=timezone.utc).timestamp(),
            metadata={"server_name": server_name, "pre_configured": True},
        )

        # Create storage key
        key = TokenStoreKey(
            user_key=synthetic_user.cache_key,
            resource=resource_str or "",
            authorization_server=auth_server_str,
            scope_fingerprint=scope_fingerprint(oauth_config.scopes or []),
        )

        # Store the token
        logger.debug(
            f"Storing token with key: user_key={key.user_key}, resource={key.resource}, auth_server={key.authorization_server}, scope_fingerprint={key.scope_fingerprint}"
        )
        await self._token_store.set(key, record)

    async def ensure_access_token(
        self,
        *,
        context: "Context",
        server_name: str,
        server_config,
        scopes: Iterable[str] | None = None,
    ) -> TokenRecord:
        oauth_config: MCPOAuthClientSettings | None = None
        if server_config and server_config.auth:
            oauth_config = getattr(server_config.auth, "oauth", None)
        if not oauth_config or not oauth_config.enabled:
            raise OAuthFlowError(
                f"Server '{server_name}' is not configured for OAuth authentication"
            )

        user = context.current_user

        # Use the same key construction logic as store_preconfigured_token to ensure consistency
        resource_str = (
            str(oauth_config.resource)
            if oauth_config.resource
            else getattr(server_config, "url", None)
        )
        auth_server_str = (
            str(oauth_config.authorization_server)
            if oauth_config.authorization_server
            else None
        )
        scope_list = (
            list(scopes) if scopes is not None else list(oauth_config.scopes or [])
        )

        # check for a globally configure token
        key = TokenStoreKey(
            user_key=create_default_user_for_preconfigured_tokens().cache_key,
            resource=resource_str,
            authorization_server=auth_server_str,
            scope_fingerprint=scope_fingerprint(scope_list),
        )

        lock = self._locks[key]

        async with lock:
            record = await self._token_store.get(key)
            if record:
                return record

        # there is no global token, look for a user specific one
        key = TokenStoreKey(
            user_key=user.cache_key,
            resource=resource_str,
            authorization_server=auth_server_str,
            scope_fingerprint=scope_fingerprint(scope_list),
        )

        lock = self._locks[key]
        async with lock:
            record = await self._token_store.get(key)
            leeway = (
                self._settings.token_store.refresh_leeway_seconds
                if self._settings and self._settings.token_store
                else 60
            )
            if record and not record.is_expired(leeway_seconds=leeway):
                return record

            # If token exists but expired, try to refresh it
            if record and record.refresh_token:
                # For refresh, we need OAuth metadata
                resource_hint = (
                    str(oauth_config.resource)
                    if oauth_config.resource
                    else getattr(server_config, "url", None)
                )
                server_url = getattr(server_config, "url", None)
                resource = normalize_resource(resource_hint, server_url)

                # Get OAuth metadata for token refresh
                parsed_resource = URL(resource)
                metadata_url = str(
                    parsed_resource.copy_with(
                        path="/.well-known/oauth-protected-resource"
                        + parsed_resource.path
                    )
                )
                resource_metadata = await self._get_resource_metadata(metadata_url)
                auth_server_url = select_authorization_server(
                    resource_metadata, str(oauth_config.authorization_server)
                )
                auth_metadata = await self._get_authorization_metadata(auth_server_url)

                try:
                    refreshed = await self._refresh_token(
                        record,
                        oauth_config=oauth_config,
                        auth_metadata=auth_metadata,
                        resource=resource,
                        scopes=scope_list,
                    )
                except TokenRefreshError:
                    await self._token_store.delete(key)
                else:
                    if refreshed:
                        await self._token_store.set(key, refreshed)
                        return refreshed
                    await self._token_store.delete(key)

            # Need to run full authorization flow - only if no token found or refresh failed
            if not record:
                resource_hint = (
                    str(oauth_config.resource)
                    if oauth_config.resource
                    else getattr(server_config, "url", None)
                )
                server_url = getattr(server_config, "url", None)
                resource = normalize_resource(resource_hint, server_url)

                # Get OAuth metadata for full authorization flow
                parsed_resource = URL(resource)
                metadata_url = str(
                    parsed_resource.copy_with(
                        path="/.well-known/oauth-protected-resource"
                        + parsed_resource.path
                    )
                )
                resource_metadata = await self._get_resource_metadata(metadata_url)
                auth_server_url = select_authorization_server(
                    resource_metadata, str(oauth_config.authorization_server)
                )
                auth_metadata = await self._get_authorization_metadata(auth_server_url)

                record = await self._flow.authorize(
                    context=context,
                    user=user,
                    server_name=server_name,
                    oauth_config=oauth_config,
                    resource=resource,
                    authorization_server_url=auth_server_url,
                    resource_metadata=resource_metadata,
                    auth_metadata=auth_metadata,
                    scopes=scope_list,
                )
                await self._token_store.set(key, record)
                return record

            # If we reach here, we have an expired token with no refresh token
            # Return it anyway - the caller will handle 401s
            return record

    async def invalidate(
        self,
        *,
        user: OAuthUserIdentity,
        resource: str,
        authorization_server: str | None,
        scopes: Iterable[str],
    ) -> None:
        key = TokenStoreKey(
            user_key=user.cache_key,
            resource=resource,
            authorization_server=authorization_server,
            scope_fingerprint=scope_fingerprint(scopes),
        )
        await self._token_store.delete(key)

    async def _refresh_token(
        self,
        record: TokenRecord,
        *,
        oauth_config: MCPOAuthClientSettings,
        auth_metadata,
        resource: str,
        scopes: Sequence[str],
    ) -> TokenRecord | None:
        if not record.refresh_token:
            return None

        token_endpoint = str(auth_metadata.token_endpoint)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": record.refresh_token,
            "client_id": oauth_config.client_id,
            "resource": resource,
        }
        if scopes:
            data["scope"] = " ".join(scopes)
        if oauth_config.client_secret:
            data["client_secret"] = oauth_config.client_secret
        if oauth_config.extra_token_params:
            data.update(oauth_config.extra_token_params)

        try:
            response = await self._http_client.post(token_endpoint, data=data)
        except httpx.HTTPError as exc:
            logger.warning("Refresh token request failed", exc_info=True)
            raise TokenRefreshError(str(exc)) from exc

        if response.status_code != 200:
            logger.warning(
                "Refresh token request returned non-success status",
                data={"status_code": response.status_code},
            )
            return None

        payload = response.json()
        new_access = payload.get("access_token")
        if not new_access:
            return None
        new_refresh = payload.get("refresh_token", record.refresh_token)
        expires_in = payload.get("expires_in")
        new_expires = record.expires_at
        if isinstance(expires_in, (int, float)):
            new_expires = time.time() + float(expires_in)

        scope_from_payload = payload.get("scope")
        if isinstance(scope_from_payload, str) and scope_from_payload.strip():
            scopes_tuple = tuple(scope_from_payload.split())
        else:
            scopes_tuple = record.scopes

        return TokenRecord(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_at=new_expires,
            scopes=scopes_tuple,
            token_type=str(payload.get("token_type", record.token_type)),
            resource=record.resource,
            authorization_server=record.authorization_server,
            metadata={"raw": payload},
        )

    async def _get_resource_metadata(self, url: str):
        cached = self._resource_metadata_cache.get(url)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        metadata = await fetch_resource_metadata(self._http_client, url)
        self._resource_metadata_cache[url] = (time.time(), metadata)
        return metadata

    async def _get_authorization_metadata(self, url: str):
        cached = self._auth_metadata_cache.get(url)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        # Construct OAuth authorization server metadata URL
        parsed_url = URL(url)
        metadata_url = str(
            parsed_url.copy_with(
                path="/.well-known/oauth-authorization-server" + parsed_url.path
            )
        )
        metadata = await fetch_authorization_server_metadata(
            self._http_client, metadata_url
        )
        self._auth_metadata_cache[url] = (time.time(), metadata)
        return metadata

    async def aclose(self) -> None:
        if self._own_http_client:
            await self._http_client.aclose()
