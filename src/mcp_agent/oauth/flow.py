"""Delegated OAuth authorization flow coordinator."""

from __future__ import annotations

import asyncio
import httpx
import uuid
import time

from json import JSONDecodeError
from typing import Any, Dict, Sequence, Iterable, Tuple
from urllib.parse import parse_qs, urlparse

from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata
from mcp.server.session import ServerSession

from mcp_agent.config import MCPOAuthClientSettings, OAuthSettings
from mcp_agent.core.context import Context
from mcp_agent.logging.logger import get_logger
from mcp_agent.oauth.callbacks import callback_registry
from mcp_agent.oauth.errors import (
    AuthorizationDeclined,
    MissingUserIdentityError,
    OAuthFlowError,
    CallbackTimeoutError,
)
from mcp_agent.oauth.identity import OAuthUserIdentity
from mcp_agent.oauth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_state,
)
from mcp_agent.oauth.records import TokenRecord
from mcp_agent.oauth.errors import OAuthFlowError

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

        # If there is no upstream session to handle auth/request, we will use a
        # local loopback callback listener on 127.0.0.1 with a configurable fixed
        # set of ports. Build candidate redirect URIs here but only start the
        # listener if we detect there is no upstream session.
        loopback_candidates: list[Tuple[str, int]] = []
        try:
            # Expect a list of ports on settings under 'loopback_ports'; if not
            # present, use a small default set that mirrors common tooling.
            ports: Iterable[int] = getattr(
                self._settings, "loopback_ports", (33418, 33419, 33420)
            )
            for p in ports:
                loopback_candidates.append((f"http://127.0.0.1:{p}/callback", p))
                loopback_candidates.append((f"http://localhost:{p}/callback", p))
        except Exception:
            pass
        for url, _ in loopback_candidates:
            if url not in redirect_options:
                redirect_options.append(url)

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
            "scopes": scopes,
            "flow_timeout_seconds": self._settings.flow_timeout_seconds,
            "state": state,
            "token_endpoint": str(auth_metadata.token_endpoint),
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": resource,
            "scope_param": scope_param,
            "extra_token_params": oauth_config.extra_token_params or {},
            "client_secret": oauth_config.client_secret,
            "issuer_str": str(getattr(auth_metadata, "issuer", "") or ""),
            "authorization_server_url": authorization_server_url,
        }

        # Try to send an auth/request upstream if available. If not available,
        # fall back to a local loopback server using the configured ports.
        result: Dict[str, Any] | None
        try:
            result = await _send_auth_request(context, request_payload)
        except AuthorizationDeclined:
            result = await _run_loopback_flow(
                flow_id=flow_id,
                state=state,
                authorize_url=authorize_url,
                loopback_candidates=loopback_candidates,
            )

        try:
            if result and result.get("url"):
                callback_data = _parse_callback_params(result["url"])
                if callback_future is not None:
                    await callback_registry.discard(flow_id)
            elif result and result.get("code"):
                callback_data = result
                if callback_future is not None:
                    await callback_registry.discard(flow_id)
            elif result and result.get("token_record"):
                if callback_future is not None:
                    await callback_registry.discard(flow_id)

                tr_data = result["token_record"]
                return TokenRecord.model_validate_json(tr_data)
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


async def _run_loopback_flow(
    *,
    flow_id: str,
    state: str,
    authorize_url: httpx.URL,
    loopback_candidates: list[tuple[str, int]],
) -> Dict[str, Any]:
    """Run a local loopback OAuth authorization flow.

    Tries a list of fixed ports; opens the browser to the authorization URL
    unchanged (provider must already have an allowed redirect matching the
    selection). Delivers the callback via callback_registry using either the
    flow id (if present) or the state parameter.
    """
    if not loopback_candidates:
        raise AuthorizationDeclined(
            "No upstream session and no loopback ports configured for OAuth flow"
        )

    # Register state so the loopback handler can resolve flow id
    try:
        await callback_registry.register_state(flow_id, state)
    except Exception:
        pass

    # Deferred import to avoid heavy deps unless needed
    import contextlib
    import socket
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs

    selected: tuple[str, int] | None = None

    # Find an available port from candidates
    for url, port in loopback_candidates:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("127.0.0.1", port))
                selected = (url, port)
                break
            except OSError:
                continue

    if selected is None:
        raise AuthorizationDeclined(
            "All configured loopback ports are busy; configure a different port list"
        )

    redirect_url, port = selected

    # Minimal request handler to capture the callback
    result_container: dict[str, Any] = {"payload": None}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http server style)
            try:
                parsed = _urlparse(self.path)
                params = {k: v[-1] for k, v in _parse_qs(parsed.query).items()}
                # Deliver by flow id or state
                delivered = False
                if flow_id:
                    delivered = (
                        threading.get_native_id() is not None
                    )  # dummy to appease linters
                    # Ignore variable; use registry
                # Prefer explicit flow delivery; else by state
                ok = False
                if flow_id:
                    ok = False  # avoid mypy confusion; we'll deliver after sending response
                result_container["payload"] = params
                # Respond immediately
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<!DOCTYPE html><html><body><h3>Authorization complete.</h3><p>You may close this window and return to MCP Agent.</p></body></html>"
                )
            except Exception:
                self.send_response(500)
                self.end_headers()

        def log_message(self, format: str, *args):  # noqa: A003 - keep server quiet
            return

    httpd: HTTPServer = HTTPServer(("127.0.0.1", port), _Handler)

    def _serve_once():
        try:
            httpd.handle_request()
        finally:
            with contextlib.suppress(Exception):
                httpd.server_close()

    t = threading.Thread(target=_serve_once, daemon=True)
    t.start()

    # Open the browser to the provider's authorize URL. The authorize URL must
    # already include a redirect_uri matching one of the provider's registered
    # values. We do not mutate the URL here because we don't know which of the
    # candidate redirect URIs the client registered; that comes from config.
    with contextlib.suppress(Exception):
        webbrowser.open(str(authorize_url), new=1, autoraise=True)

    # Wait for one request or timeout
    # Simple polling with backoff; we keep this lightweight.
    import time as _time

    deadline = _time.time() + 300.0
    while _time.time() < deadline:
        if result_container["payload"] is not None:
            break
        _time.sleep(0.1)

    payload = result_container["payload"]
    if not payload:
        raise CallbackTimeoutError("Timed out waiting for loopback OAuth callback")

    # Try to deliver via flow id first, else by state
    delivered = await callback_registry.deliver(flow_id, payload)
    if not delivered:
        delivered = await callback_registry.deliver_by_state(
            payload.get("state", ""), payload
        )
    if not delivered:
        # If still not delivered, just return the parsed payload to the caller
        # (flow will proceed using the returned data).
        return payload
    return payload
