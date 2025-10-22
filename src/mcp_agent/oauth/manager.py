"""Token management for downstream OAuth-protected MCP servers."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Sequence, Tuple, TYPE_CHECKING

import httpx
from httpx import URL

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.errors import (
    MissingUserIdentityError,
    OAuthFlowError,
    TokenRefreshError,
)
from mcp_agent.oauth.flow import AuthorizationFlowCoordinator
from mcp_agent.oauth.identity import (
    DEFAULT_PRECONFIGURED_IDENTITY,
    OAuthUserIdentity,
)
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

from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedOAuthContext:
    """Resolved metadata for interacting with an OAuth authorization server."""

    resource: str
    resource_metadata: ProtectedResourceMetadata
    authorization_server_url: str
    authorization_metadata: OAuthMetadata
    issuer: str
    scopes: Tuple[str, ...]


def _dedupe(sequence: Iterable[OAuthUserIdentity]) -> list[OAuthUserIdentity]:
    seen = set()
    result: list[OAuthUserIdentity] = []
    for identity in sequence:
        if identity is None:
            continue
        key = identity.cache_key
        if key in seen:
            continue
        seen.add(key)
        result.append(identity)
    return result


def _canonicalize_url(url: str) -> str:
    parsed = URL(url)
    if parsed.scheme not in ("http", "https"):
        raise OAuthFlowError(f"Unsupported URL scheme for canonicalization: {url}")
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


def _candidate_resource_metadata_urls(parsed_resource: URL) -> list[str]:
    base = parsed_resource.copy_with(path="", query=None, fragment=None)
    path = parsed_resource.path.lstrip("/")
    candidates = []
    if path:
        candidates.append(
            str(base.copy_with(path=f"/.well-known/oauth-protected-resource/{path}"))
        )
    candidates.append(str(base.copy_with(path="/.well-known/oauth-protected-resource")))
    # remove duplicates while preserving order
    seen = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _candidate_authorization_metadata_urls(
    parsed_authorization_server: URL,
) -> list[str]:
    base = parsed_authorization_server.copy_with(path="", query=None, fragment=None)
    path = parsed_authorization_server.path.lstrip("/")
    candidates = []
    if path:
        candidates.append(
            str(base.copy_with(path=f"/.well-known/oauth-authorization-server/{path}"))
        )
    candidates.append(
        str(base.copy_with(path="/.well-known/oauth-authorization-server"))
    )
    seen = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


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
        # Cache resource metadata by canonical resource string
        self._resource_metadata_cache: Dict[
            str, tuple[float, ProtectedResourceMetadata]
        ] = {}
        # Cache authorization metadata by canonical issuer
        self._auth_metadata_cache: Dict[str, tuple[float, OAuthMetadata]] = {}
        self._default_identity = DEFAULT_PRECONFIGURED_IDENTITY

    async def store_preconfigured_token(
        self,
        *,
        context: "Context",
        server_name: str,
        server_config,
    ) -> None:
        """Store a pre-configured token defined in the MCP configuration."""
        oauth_config: MCPOAuthClientSettings | None = None
        if server_config and server_config.auth:
            oauth_config = getattr(server_config.auth, "oauth", None)
        if not oauth_config or not oauth_config.enabled:
            return
        if not oauth_config.access_token:
            logger.debug(
                "No preconfigured access token provided for server '%s'; skipping",
                server_name,
            )
            return

        resolved = await self._resolve_oauth_context(
            context=context,
            server_name=server_name,
            server_config=server_config,
            oauth_config=oauth_config,
            requested_scopes=oauth_config.scopes or [],
        )

        from datetime import datetime, timezone

        record = TokenRecord(
            access_token=oauth_config.access_token,
            refresh_token=oauth_config.refresh_token,
            scopes=tuple(oauth_config.scopes or resolved.scopes),
            expires_at=oauth_config.expires_at,
            token_type=oauth_config.token_type,
            resource=resolved.resource,
            authorization_server=resolved.issuer,
            obtained_at=datetime.now(tz=timezone.utc).timestamp(),
            metadata={
                "server_name": server_name,
                "pre_configured": True,
                "authorization_server_url": resolved.authorization_server_url,
            },
        )

        key = self._build_store_key(
            self._default_identity,
            resolved.resource,
            resolved.issuer,
            record.scopes,
        )
        logger.debug(
            f"Caching preconfigured token for server '{server_name}' under identity "
            f"'{self._default_identity.cache_key}'"
        )
        await self._token_store.set(key, record)

    async def store_user_token(
        self,
        *,
        context: "Context",
        user: OAuthUserIdentity,
        server_name: str,
        server_config,
        token_data: Dict[str, object],
        workflow_name: str | None = None,
    ) -> None:
        """Persist a token supplied through the workflow pre-auth endpoint."""
        if not token_data.get("access_token"):
            raise OAuthFlowError("Missing access_token in token payload")

        oauth_config: MCPOAuthClientSettings | None = None
        if server_config and server_config.auth:
            oauth_config = getattr(server_config.auth, "oauth", None)
        if not oauth_config or not oauth_config.enabled:
            raise OAuthFlowError(
                f"Server '{server_name}' is not configured for OAuth authentication"
            )

        provided_scopes = tuple(token_data.get("scopes") or [])
        resolved = await self._resolve_oauth_context(
            context=context,
            server_name=server_name,
            server_config=server_config,
            oauth_config=oauth_config,
            requested_scopes=provided_scopes or oauth_config.scopes or [],
        )

        # Verify authorization server alignment if the caller provided one.
        provided_auth_server = token_data.get("authorization_server")
        if provided_auth_server:
            provided_canonical = _canonicalize_url(str(provided_auth_server))
            if provided_canonical != resolved.issuer:
                raise OAuthFlowError(
                    "authorization_server does not match configured authorization server"
                )

        from datetime import datetime, timezone

        scopes_tuple = (
            tuple(provided_scopes)
            if provided_scopes
            else tuple(oauth_config.scopes or resolved.scopes)
        )
        if resolved.scopes and scopes_tuple:
            missing = set(resolved.scopes) - set(scopes_tuple)
            if missing:
                logger.warning(
                    "Stored token for server '%s' missing expected scopes: %s",
                    server_name,
                    sorted(missing),
                )

        record = TokenRecord(
            access_token=str(token_data["access_token"]),
            refresh_token=token_data.get("refresh_token"),
            scopes=scopes_tuple,
            expires_at=token_data.get("expires_at"),
            token_type=str(token_data.get("token_type", "Bearer")),
            resource=resolved.resource,
            authorization_server=resolved.issuer,
            obtained_at=datetime.now(tz=timezone.utc).timestamp(),
            metadata={
                "server_name": server_name,
                "authorization_server_url": resolved.authorization_server_url,
                "pre_configured": False,
                "workflow_name": workflow_name,
                "session_id": getattr(context, "session_id", None),
            },
        )

        key = self._build_store_key(
            user,
            resolved.resource,
            resolved.issuer,
            record.scopes,
        )

        await self._token_store.set(key, record)

    async def get_access_token_if_present(
        self,
        *,
        context: "Context",
        server_name: str,
        server_config,
        scopes: Iterable[str] | None = None,
        identity: OAuthUserIdentity | None = None,
    ) -> TokenRecord | None:
        oauth_config: MCPOAuthClientSettings | None = None
        if server_config and server_config.auth:
            oauth_config = getattr(server_config.auth, "oauth", None)
        if not oauth_config or not oauth_config.enabled:
            raise OAuthFlowError(
                f"Server '{server_name}' is not configured for OAuth authentication"
            )

        requested_scopes = (
            list(scopes) if scopes is not None else list(oauth_config.scopes or [])
        )

        resolved = await self._resolve_oauth_context(
            context=context,
            server_name=server_name,
            server_config=server_config,
            oauth_config=oauth_config,
            requested_scopes=requested_scopes,
        )

        context_identity = None
        try:
            from mcp_agent.server import app_server

            context_identity = app_server.get_current_identity()
        except Exception:
            context_identity = None
        session_identity = self._session_identity(context)

        identity_candidates = [
            identity,
            context_identity,
            session_identity,
            self._default_identity,
        ]
        identities = _dedupe(identity_candidates)
        logger.debug(
            "Resolved identity candidates for token acquisition",
            data={
                "server": server_name,
                "candidates": [candidate.cache_key for candidate in identities],
            },
        )
        if not identities:
            raise MissingUserIdentityError(
                "No authenticated user available for OAuth authorization"
            )

        leeway = (
            self._settings.token_store.refresh_leeway_seconds
            if self._settings.token_store
            else 60
        )

        for identity in identities:
            key = self._build_store_key(
                identity,
                resolved.resource,
                resolved.issuer,
                resolved.scopes,
            )
            lock = self._locks[key]
            async with lock:
                record = await self._token_store.get(key)
                if record and not record.is_expired(leeway_seconds=leeway):
                    logger.debug(
                        "Token cache hit",
                        data={
                            "server": server_name,
                            "identity": identity.cache_key,
                            "resource": resolved.resource,
                        },
                    )
                    return record

                if record and record.refresh_token:
                    try:
                        refreshed = await self._refresh_token(
                            record,
                            oauth_config=oauth_config,
                            auth_metadata=resolved.authorization_metadata,
                            resource=resolved.resource,
                            scopes=resolved.scopes,
                        )
                    except TokenRefreshError as exc:
                        logger.warning(
                            "Failed to refresh token for identity '%s': %s",
                            identity.cache_key,
                            exc,
                        )
                        await self._token_store.delete(key)
                        continue

                    if refreshed:
                        refreshed = refreshed.model_copy(
                            update={
                                "resource": resolved.resource,
                                "authorization_server": resolved.issuer,
                            }
                        )
                        await self._token_store.set(key, refreshed)
                        return refreshed

                    await self._token_store.delete(key)
        return None

    async def ensure_access_token(
        self,
        *,
        context: "Context",
        server_name: str,
        server_config,
        scopes: Iterable[str] | None = None,
        identity: OAuthUserIdentity | None = None,
    ) -> TokenRecord:
        oauth_config: MCPOAuthClientSettings | None = None
        if server_config and server_config.auth:
            oauth_config = getattr(server_config.auth, "oauth", None)
        if not oauth_config or not oauth_config.enabled:
            raise OAuthFlowError(
                f"Server '{server_name}' is not configured for OAuth authentication"
            )

        requested_scopes = (
            list(scopes) if scopes is not None else list(oauth_config.scopes or [])
        )
        resolved = await self._resolve_oauth_context(
            context=context,
            server_name=server_name,
            server_config=server_config,
            oauth_config=oauth_config,
            requested_scopes=requested_scopes,
        )

        context_identity = None
        try:
            from mcp_agent.server import app_server

            context_identity = app_server.get_current_identity()
        except Exception:
            context_identity = None
        session_identity = self._session_identity(context)

        identity_candidates = [
            identity,
            context_identity,
            session_identity,
            self._default_identity,
        ]
        identities = _dedupe(identity_candidates)
        if not identities:
            raise MissingUserIdentityError(
                "No authenticated user available for OAuth authorization"
            )

        leeway = (
            self._settings.token_store.refresh_leeway_seconds
            if self._settings.token_store
            else 60
        )

        last_error: Exception | None = None
        for identity in identities:
            key = self._build_store_key(
                identity,
                resolved.resource,
                resolved.issuer,
                resolved.scopes,
            )
            lock = self._locks[key]
            async with lock:
                record = await self._token_store.get(key)
                if record and not record.is_expired(leeway_seconds=leeway):
                    return record

                if record and record.refresh_token:
                    try:
                        refreshed = await self._refresh_token(
                            record,
                            oauth_config=oauth_config,
                            auth_metadata=resolved.authorization_metadata,
                            resource=resolved.resource,
                            scopes=resolved.scopes,
                        )
                    except TokenRefreshError as exc:
                        logger.warning(
                            "Failed to refresh token for identity '%s': %s",
                            identity.cache_key,
                            exc,
                        )
                        await self._token_store.delete(key)
                        last_error = exc
                        continue

                    if refreshed:
                        refreshed = refreshed.model_copy(
                            update={
                                "resource": resolved.resource,
                                "authorization_server": resolved.issuer,
                            }
                        )
                        await self._token_store.set(key, refreshed)
                        return refreshed

                    await self._token_store.delete(key)

        # Only authenticated users (non-default identity) can initiate new flows.
        flow_identity = next(  # type: ignore[arg-type]
            (
                cand
                for cand in identity_candidates
                if cand is not None and cand != self._default_identity
            ),
            None,
        )
        if flow_identity is None:
            if last_error:
                raise last_error
            raise MissingUserIdentityError(
                "No authenticated user available to initiate OAuth authorization flow"
            )

        user_key = self._build_store_key(
            flow_identity,
            resolved.resource,
            resolved.issuer,
            resolved.scopes,
        )

        lock = self._locks[user_key]
        async with lock:
            # Double-check to avoid duplicate authorization while we awaited the lock.
            existing = await self._token_store.get(user_key)
            if existing and not existing.is_expired(leeway_seconds=leeway):
                return existing

            record = await self._flow.authorize(
                context=context,
                user=flow_identity,
                server_name=server_name,
                oauth_config=oauth_config,
                resource=resolved.resource,
                authorization_server_url=resolved.authorization_server_url,
                resource_metadata=resolved.resource_metadata,
                auth_metadata=resolved.authorization_metadata,
                scopes=resolved.scopes,
            )
            record = record.model_copy(
                update={
                    "resource": resolved.resource,
                    "authorization_server": resolved.issuer,
                }
            )

            await self._token_store.set(user_key, record)
            logger.debug(
                "Stored new access token via authorization flow",
                data={
                    "server": server_name,
                    "identity": flow_identity.cache_key,
                    "resource": resolved.resource,
                },
            )
            return record

    async def invalidate(
        self,
        *,
        identity: OAuthUserIdentity,
        resource: str,
        authorization_server: str | None,
        scopes: Iterable[str],
    ) -> None:
        canonical_resource = normalize_resource(resource, resource)
        canonical_auth_server = (
            _canonicalize_url(authorization_server)
            if authorization_server
            else authorization_server
        )
        key = self._build_store_key(
            identity,
            canonical_resource,
            canonical_auth_server or "",
            tuple(scopes),
        )
        await self._token_store.delete(key)
        if (
            identity.cache_key != self._default_identity.cache_key
            and canonical_auth_server
        ):
            default_key = self._build_store_key(
                self._default_identity,
                canonical_resource,
                canonical_auth_server,
                tuple(scopes),
            )
            await self._token_store.delete(default_key)

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
            scopes_tuple = tuple(scopes) if scopes else record.scopes

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

    async def _resolve_oauth_context(
        self,
        *,
        context: "Context",
        server_name: str,
        server_config,
        oauth_config: MCPOAuthClientSettings,
        requested_scopes: Iterable[str],
    ) -> ResolvedOAuthContext:
        resource_hint = (
            str(oauth_config.resource)
            if oauth_config.resource
            else getattr(server_config, "url", None)
        )
        server_url = getattr(server_config, "url", None)
        resource = normalize_resource(resource_hint, server_url)
        parsed_resource = URL(resource)

        resource_metadata = await self._get_resource_metadata(resource, parsed_resource)

        preferred_auth_server = (
            str(oauth_config.authorization_server)
            if oauth_config.authorization_server
            else None
        )
        authorization_server_url = select_authorization_server(
            resource_metadata, preferred_auth_server
        )
        parsed_auth_server = URL(authorization_server_url)
        authorization_metadata = await self._get_authorization_metadata(
            authorization_server_url, parsed_auth_server
        )

        issuer = getattr(authorization_metadata, "issuer", None)
        issuer_str = _canonicalize_url(str(issuer or authorization_server_url))

        scopes_tuple = tuple(requested_scopes or oauth_config.scopes or [])

        return ResolvedOAuthContext(
            resource=resource,
            resource_metadata=resource_metadata,
            authorization_server_url=authorization_server_url,
            authorization_metadata=authorization_metadata,
            issuer=issuer_str,
            scopes=scopes_tuple,
        )

    async def _get_resource_metadata(
        self, canonical_resource: str, parsed_resource: URL
    ) -> ProtectedResourceMetadata:
        cached = self._resource_metadata_cache.get(canonical_resource)
        if cached and time.time() - cached[0] < 300:
            return cached[1]

        last_exception: Exception | None = None
        for url in _candidate_resource_metadata_urls(parsed_resource):
            try:
                metadata = await fetch_resource_metadata(self._http_client, url)
            except httpx.HTTPError as exc:
                last_exception = exc
                continue
            else:
                self._resource_metadata_cache[canonical_resource] = (
                    time.time(),
                    metadata,
                )
                return metadata

        raise OAuthFlowError(
            f"Failed to fetch resource metadata for '{canonical_resource}'"
        ) from last_exception

    async def _get_authorization_metadata(
        self, authorization_server_url: str, parsed_authorization_server: URL
    ) -> OAuthMetadata:
        canonical_base = _canonicalize_url(authorization_server_url)
        cached = self._auth_metadata_cache.get(canonical_base)
        if cached and time.time() - cached[0] < 300:
            return cached[1]

        last_exception: Exception | None = None
        for url in _candidate_authorization_metadata_urls(parsed_authorization_server):
            try:
                metadata = await fetch_authorization_server_metadata(
                    self._http_client, url
                )
            except httpx.HTTPError as exc:
                last_exception = exc
                continue
            else:
                issuer = getattr(metadata, "issuer", None)
                cache_key = _canonicalize_url(str(issuer)) if issuer else canonical_base
                self._auth_metadata_cache[cache_key] = (time.time(), metadata)
                return metadata

        raise OAuthFlowError(
            f"Failed to fetch authorization server metadata from '{authorization_server_url}'"
        ) from last_exception

    def _build_store_key(
        self,
        identity: OAuthUserIdentity,
        resource: str,
        authorization_server: str,
        scopes: Sequence[str],
    ) -> TokenStoreKey:
        return TokenStoreKey(
            user_key=identity.cache_key,
            resource=resource,
            authorization_server=authorization_server,
            scope_fingerprint=scope_fingerprint(scopes),
        )

    async def aclose(self) -> None:
        if self._own_http_client:
            await self._http_client.aclose()
        close = getattr(self._token_store, "aclose", None)
        if callable(close):
            await close()

    def _session_identity(self, context: "Context") -> OAuthUserIdentity | None:
        in_temporal = False
        try:
            from temporalio import workflow as _wf  # type: ignore
            from temporalio import activity as _a  # type: ignore

            try:
                in_temporal = bool(_wf.in_workflow()) or bool(_a.in_activity())
            except Exception:
                in_temporal = False
        except Exception:
            in_temporal = False

        # Temporal workflows/activities carry their own execution identity.
        if in_temporal:
            try:
                from mcp_agent.executor.temporal.temporal_context import (
                    get_execution_id as _get_exec_id,
                )
                from mcp_agent.server import app_server

                execution_id = _get_exec_id()
                if execution_id:
                    identity = app_server._get_identity_for_execution(execution_id)
                    if identity is not None:
                        return identity
            except Exception:
                pass

        session_id = None
        if in_temporal:
            session_id = getattr(context, "session_id", None)

        if session_id:
            try:
                from mcp_agent.server import app_server

                identity = app_server.get_identity_for_session(session_id, context)
                if identity is not None:
                    logger.debug(
                        "Resolved session identity from registry",
                        data={
                            "session_id": session_id,
                            "identity": identity.cache_key,
                        },
                    )
                    return identity
            except Exception as exc:
                logger.debug(
                    "Failed to resolve session identity from registry",
                    data={"session_id": session_id, "error": repr(exc)},
                )
            fallback = OAuthUserIdentity(
                provider="mcp-session", subject=str(session_id)
            )
            logger.debug(
                "Falling back to synthetic session identity",
                data={"session_id": session_id, "identity": fallback.cache_key},
            )
            return fallback

        logger.debug(
            "TokenManager no session identity resolved",
            data={"context_session_id": getattr(context, "session_id", None)},
        )
        return None
