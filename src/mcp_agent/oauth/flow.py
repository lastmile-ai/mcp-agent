"""Delegated OAuth authorization flow coordinator."""

from __future__ import annotations

import asyncio
import time
import uuid
from json import JSONDecodeError
from typing import Any, Dict, Sequence
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata
from mcp.server.session import ServerSession

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.core.context import Context
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.callbacks import callback_registry
from mcp_agent.oauth.errors import (
    AuthorizationDeclined,
    CallbackTimeoutError,
    MissingUserIdentityError,
    OAuthFlowError,
)
from mcp_agent.oauth.identity import OAuthUserIdentity
from mcp_agent.oauth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_state,
)
from mcp_agent.oauth.records import TokenRecord

logger = get_logger(__name__)


class AuthorizationFlowCoordinator:
    """Handles the interactive OAuth Authorization Code flow via MCP clients."""

    def __init__(self, *, http_client: httpx.AsyncClient, settings: OAuthSettings):
        self._http_client = http_client
        self._settings = settings

    async def authorize(
        self,
        *,
        context: Context,
        user: OAuthUserIdentity,
        server_name: str,
        oauth_config: MCPOAuthClientSettings,
        resource: str,
        authorization_server_url: str,
        resource_metadata: ProtectedResourceMetadata,
        auth_metadata: OAuthMetadata,
        scopes: Sequence[str],
    ) -> TokenRecord:
        if not user:
            raise MissingUserIdentityError(
                "Cannot begin OAuth flow without authenticated MCP user"
            )

        client_id = oauth_config.client_id
        if not client_id:
            raise OAuthFlowError(
                f"No OAuth client_id configured for server '{server_name}'."
            )

        redirect_options = list(oauth_config.redirect_uri_options or [])
        flow_id = uuid.uuid4().hex
        internal_redirect = None
        if oauth_config.use_internal_callback and self._settings.callback_base_url:
            internal_redirect = f"{str(self._settings.callback_base_url).rstrip('/')}/internal/oauth/callback/{flow_id}"
            redirect_options.insert(0, internal_redirect)

        if not redirect_options:
            raise OAuthFlowError(
                "No redirect URI options configured for OAuth authorization flow"
            )

        redirect_uri = redirect_options[0]

        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        state = generate_state()
        scope_param = " ".join(scopes)

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_param,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        }

        # add extra params if any
        if oauth_config.extra_authorize_params:
            params.update(oauth_config.extra_authorize_params)

        import urllib.parse

        authorize_url = httpx.URL(
            str(auth_metadata.authorization_endpoint)
            + "?"
            + urllib.parse.urlencode(params)
        )

        callback_future = None
        if internal_redirect is not None:
            callback_future = await callback_registry.create_handle(flow_id)

        request_payload = {
            "url": str(authorize_url),
            "message": f"Authorization required for {server_name}",
            "redirect_uri_options": redirect_options,
            "flow_id": flow_id,
            "server_name": server_name,
            "scopes": scope_param,
        }

        result = await _send_auth_request(context, request_payload)

        try:
            if result and result.get("url"):
                callback_data = _parse_callback_params(result["url"])
                if callback_future is not None:
                    await callback_registry.discard(flow_id)
            elif result and result.get("code"):
                callback_data = result
                if callback_future is not None:
                    await callback_registry.discard(flow_id)
            elif callback_future is not None:
                timeout = self._settings.flow_timeout_seconds or 300
                try:
                    callback_data = await asyncio.wait_for(
                        callback_future, timeout=timeout
                    )
                except asyncio.TimeoutError as exc:
                    raise CallbackTimeoutError(
                        f"Timed out waiting for OAuth callback after {timeout} seconds"
                    ) from exc
            else:
                raise AuthorizationDeclined(
                    "Authorization request was declined by the user"
                )
        finally:
            if callback_future is not None:
                await callback_registry.discard(flow_id)

        error = callback_data.get("error")
        if error:
            description = callback_data.get("error_description") or error
            raise OAuthFlowError(f"Authorization server returned error: {description}")

        returned_state = callback_data.get("state")
        if returned_state != state:
            raise OAuthFlowError("State mismatch detected in OAuth callback")

        authorization_code = callback_data.get("code")
        if not authorization_code:
            raise OAuthFlowError("Authorization callback did not include code")

        token_endpoint = str(auth_metadata.token_endpoint)
        data: Dict[str, Any] = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": resource,
        }
        if scope_param:
            data["scope"] = scope_param
        if oauth_config.extra_token_params:
            data.update(oauth_config.extra_token_params)

        auth = None
        if oauth_config.client_secret:
            data["client_secret"] = oauth_config.client_secret

        token_response = await self._http_client.post(
            token_endpoint, data=data, auth=auth, headers={"Accept": "application/json"}
        )
        token_response.raise_for_status()

        try:
            callback_data = token_response.json()
        except JSONDecodeError:
            callback_data = _parse_callback_params("?" + token_response.text)

        access_token = callback_data.get("access_token")
        if not access_token:
            raise OAuthFlowError("Token endpoint response missing access_token")
        refresh_token = callback_data.get("refresh_token")
        expires_in = callback_data.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)):
            expires_at = time.time() + float(expires_in)

        scope_from_payload = callback_data.get("scope")
        if isinstance(scope_from_payload, str) and scope_from_payload.strip():
            effective_scopes = tuple(scope_from_payload.split())
        else:
            effective_scopes = tuple(scopes)

        issuer = getattr(auth_metadata, "issuer", None)
        issuer_str = str(issuer) if issuer else authorization_server_url

        return TokenRecord(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=effective_scopes,
            token_type=str(callback_data.get("token_type", "Bearer")),
            resource=resource,
            authorization_server=issuer_str,
            metadata={
                "raw": token_response.text,
                "authorization_server_url": authorization_server_url,
            },
        )


def _parse_callback_params(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    params = {}
    params.update({k: v[-1] for k, v in parse_qs(parsed.query).items()})
    if parsed.fragment:
        params.update({k: v[-1] for k, v in parse_qs(parsed.fragment).items()})
    return params


async def _send_auth_request(
    context: Context, payload: Dict[str, Any]
) -> Dict[str, Any]:
    session = getattr(context, "upstream_session", None)

    if session and isinstance(session, ServerSession):
        rpc = getattr(session, "rpc", None)
        if rpc and hasattr(rpc, "request"):
            return await rpc.request("auth/request", payload)
    raise AuthorizationDeclined(
        "No upstream MCP session available to prompt user for authorization"
    )
