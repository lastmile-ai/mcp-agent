"""httpx.Auth adapter that acquires tokens via TokenManager."""

from __future__ import annotations

import httpx

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.oauth.manager import TokenManager
    from mcp_agent.core.context import Context
    from mcp_agent.oauth.identity import OAuthUserIdentity


class OAuthHttpxAuth(httpx.Auth):
    requires_request_body = True

    def __init__(
        self,
        *,
        token_manager: "TokenManager",
        context: "Context",
        server_name: str,
        server_config,
        scopes=None,
        identity_resolver: Callable[[], "OAuthUserIdentity | None"] | None = None,
    ) -> None:
        self._token_manager = token_manager
        self._context = context
        self._server_name = server_name
        self._server_config = server_config
        self._scopes = list(scopes) if scopes is not None else None
        self._identity_resolver = identity_resolver

    def _resolve_identity(self) -> "OAuthUserIdentity | None":
        if self._identity_resolver is not None:
            return self._identity_resolver()

        from mcp_agent.oauth.errors import MissingUserIdentityError
        from mcp_agent.oauth.identity import (
            is_authenticated_identity,
            resolve_identity_from_auth_context,
        )

        has_auth_user, auth_user_identity = resolve_identity_from_auth_context()
        if has_auth_user:
            if not is_authenticated_identity(auth_user_identity):
                raise MissingUserIdentityError(
                    "Authenticated request is missing a valid subject ('sub') claim"
                )
            return auth_user_identity

        try:
            from mcp_agent.server import app_server

            return app_server.get_current_identity()
        except Exception:
            return None

    async def async_auth_flow(self, request: httpx.Request):
        identity = self._resolve_identity()

        try:
            token_record = await self._token_manager.ensure_access_token(
                context=self._context,
                server_name=self._server_name,
                server_config=self._server_config,
                scopes=self._scopes,
                identity=identity,
            )
        except Exception:
            raise
        request.headers["Authorization"] = (
            f"{token_record.token_type} {token_record.access_token}"
        )
        response = yield request

        if response.status_code != 401:
            return

        if identity is None:
            identity = self._resolve_identity()
        if identity is None:
            from mcp_agent.oauth.errors import MissingUserIdentityError
            from mcp_agent.oauth.identity import (
                DEFAULT_PRECONFIGURED_IDENTITY,
                is_authorization_enabled,
            )

            if is_authorization_enabled(self._context):
                raise MissingUserIdentityError(
                    "No authenticated user available for OAuth retry"
                )
            identity = DEFAULT_PRECONFIGURED_IDENTITY
        if identity is None:
            return

        await self._token_manager.invalidate(
            identity=identity,
            resource=token_record.resource or "",
            authorization_server=token_record.authorization_server,
            scopes=token_record.scopes,
        )

        refreshed_record = await self._token_manager.ensure_access_token(
            context=self._context,
            server_name=self._server_name,
            server_config=self._server_config,
            scopes=self._scopes,
            identity=identity,
        )

        # Create a new request with the refreshed token while preserving the original body.
        copy_fn = getattr(request, "copy", None)
        if callable(copy_fn):
            retry_request = copy_fn()
        else:
            retry_request = httpx.Request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                content=request.content,
                extensions=dict(request.extensions),
            )
        retry_request.headers["Authorization"] = (
            f"{refreshed_record.token_type} {refreshed_record.access_token}"
        )
        yield retry_request
