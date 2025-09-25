"""httpx.Auth adapter that acquires tokens via TokenManager."""

from __future__ import annotations

import httpx

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.oauth.manager import TokenManager
    from mcp_agent.core.context import Context


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
    ) -> None:
        self._token_manager = token_manager
        self._context = context
        self._server_name = server_name
        self._server_config = server_config
        self._scopes = list(scopes) if scopes is not None else None

    async def async_auth_flow(self, request: httpx.Request):
        try:
            token_record = await self._token_manager.ensure_access_token(
                context=self._context,
                server_name=self._server_name,
                server_config=self._server_config,
                scopes=self._scopes,
            )
        except Exception as e:
            raise
        request.headers["Authorization"] = (
            f"{token_record.token_type} {token_record.access_token}"
        )
        response = yield request

        if response.status_code != 401:
            return

        user = self._context.current_user
        if user is None:
            return

        await self._token_manager.invalidate(
            user=user,
            resource=token_record.resource or "",
            authorization_server=token_record.authorization_server,
            scopes=token_record.scopes,
        )

        refreshed_record = await self._token_manager.ensure_access_token(
            context=self._context,
            server_name=self._server_name,
            server_config=self._server_config,
            scopes=self._scopes,
        )

        # Create a new request with the refreshed token
        retry_request = httpx.Request(
            method=request.method,
            url=request.url,
            headers=request.headers.copy(),
            content=request.content,
        )
        retry_request.headers["Authorization"] = (
            f"{refreshed_record.token_type} {refreshed_record.access_token}"
        )
        yield retry_request
