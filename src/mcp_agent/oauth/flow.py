"""Delegated OAuth authorization flow coordinator."""

from __future__ import annotations

import asyncio
import contextlib
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
# Keep import list minimal in this module to avoid warnings; OAuthFlowError imported elsewhere when needed

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

        include_resource = getattr(oauth_config, "include_resource_parameter", True)
        logger.debug(
            "Starting OAuth authorization",
            data={
                "server": server_name,
                "include_resource_param": include_resource,
                "resource": resource,
            },
        )

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_param,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if include_resource and resource:
            params["resource"] = resource

        # add extra params if any
        if oauth_config.extra_authorize_params:
            params.update(oauth_config.extra_authorize_params)

        import urllib.parse

        authorize_url = httpx.URL(
            str(auth_metadata.authorization_endpoint).rstrip("/")
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
        }
        if include_resource and resource:
            request_payload["resource"] = resource
        if scope_param:
            request_payload["scope_param"] = scope_param
        if oauth_config.extra_token_params:
            request_payload["extra_token_params"] = oauth_config.extra_token_params
        request_payload["client_secret"] = oauth_config.client_secret
        request_payload["issuer_str"] = str(getattr(auth_metadata, "issuer", "") or "")
        request_payload["authorization_server_url"] = authorization_server_url

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
            if result and result.get("_loopback_redirect_uri"):
                redirect_uri = result.pop("_loopback_redirect_uri")
                request_payload["redirect_uri"] = redirect_uri

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
            with contextlib.suppress(Exception):
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
        }
        if scope_param:
            data["scope"] = scope_param
        if oauth_config.extra_token_params:
            data.update(oauth_config.extra_token_params)
        if include_resource and resource:
            data["resource"] = resource

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
            logger.error(
                "Token endpoint response missing access_token",
                data={"response": callback_data, "text": token_response.text},
            )
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

    import socket
    import webbrowser
    from urllib.parse import (
        urlencode as _urlencode,
        urlparse as _p,
        urlunparse as _u,
        urlsplit as _urlsplit,
        parse_qs as _parse_qs,
    )

    selected: tuple[str, int] | None = None

    # Find an available port from candidates
    for url, port in loopback_candidates:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                selected = (url, port)
                break
            except OSError:
                continue

    if selected is None:
        cfg_ports = ",".join(str(p) for _, p in loopback_candidates) or "(none)"
        raise AuthorizationDeclined(
            f"All configured loopback ports are busy (tried: {cfg_ports}); set oauth.loopback_ports to a different list"
        )

    redirect_url, port = selected

    loop = asyncio.get_running_loop()
    payload_future: asyncio.Future[Dict[str, Any]] = loop.create_future()

    async def _handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            parts = request_line.decode("latin-1").strip().split(" ")
            if len(parts) < 2:
                return
            target = parts[1]

            # Consume headers until blank line
            while True:
                header = await reader.readline()
                if not header or header in (b"\r\n", b"\n"):
                    break

            parsed_target = _urlsplit(target)
            params = {k: v[-1] for k, v in _parse_qs(parsed_target.query).items()}
            is_auth_callback = bool(params.get("code") or params.get("error"))
            if is_auth_callback and not payload_future.done():
                payload_future.set_result(params)

            body = (
                "<!DOCTYPE html><html><body><h3>Authorization complete.</h3>"
                "<p>You may close this window and return to MCP Agent.</p></body></html>"
            )
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                "Connection: close\r\n\r\n"
                f"{body}"
            )
            writer.write(response.encode("utf-8"))
            await writer.drain()
        except Exception:
            with contextlib.suppress(Exception):
                writer.write(
                    b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n"
                )
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_server(_handle, "127.0.0.1", port)

    try:
        # Ensure the authorization URL uses the selected redirect_uri.
        parsed = _p(str(authorize_url))
        q = {k: v[-1] for k, v in _parse_qs(parsed.query).items()}
        q["redirect_uri"] = redirect_url
        final_url = _u(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                _urlencode(q),
                parsed.fragment,
            )
        )

        # Mask sensitive query parameters in logs
        try:
            masked_q = dict(q)
            for sensitive in ("state", "code_challenge"):
                if sensitive in masked_q:
                    masked_q[sensitive] = "***"
            masked_url = _u(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    _urlencode(masked_q),
                    parsed.fragment,
                )
            )
        except Exception:
            masked_url = "(redacted)"

        logger.info(
            "OAuth loopback flow started",
            data={
                "redirect_uri": redirect_url,
                "authorization_url": masked_url,
                "ports": sorted({p for _, p in loopback_candidates}),
                "selected_port": port,
            },
        )

        # Open the browser to the adjusted URL, but always print the URL
        print(
            "\nOpen the following URL in your browser to authorize if it does not open automatically:\n"
            f"  {final_url}\n"
        )
        with contextlib.suppress(Exception):
            webbrowser.open(final_url, new=1, autoraise=True)

        try:
            payload = await asyncio.wait_for(payload_future, timeout=300.0)
        except asyncio.TimeoutError as exc:
            raise CallbackTimeoutError(
                "Timed out waiting for loopback OAuth callback"
            ) from exc
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()

    payload["_loopback_redirect_uri"] = redirect_url

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
