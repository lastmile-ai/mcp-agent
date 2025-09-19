from typing import Any, Dict, Optional

import os
import httpx

from urllib.parse import quote


def _resolve_gateway_url(
    *,
    gateway_url: Optional[str] = None,
    context_gateway_url: Optional[str] = None,
) -> str:
    """Resolve the base URL for the MCP gateway.

    Precedence:
    1) Explicit override (gateway_url parameter)
    2) Context-provided URL (context_gateway_url)
    3) Environment variable MCP_GATEWAY_URL
    4) Fallback to http://127.0.0.1:8000 (dev default)
    """
    # Highest precedence: explicit override
    if gateway_url:
        return gateway_url.rstrip("/")

    # Next: context-provided URL (e.g., from Temporal workflow memo)
    if context_gateway_url:
        return context_gateway_url.rstrip("/")

    # Next: environment variable
    env_url = os.environ.get("MCP_GATEWAY_URL")
    if env_url:
        return env_url.rstrip("/")

    # Fallback: default local server
    return "http://127.0.0.1:8000"


async def log_via_proxy(
    execution_id: str,
    level: str,
    namespace: str,
    message: str,
    data: Dict[str, Any] | None = None,
    *,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> bool:
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/workflows/log"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
        headers["Authorization"] = f"Bearer {tok}"
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url,
                json={
                    "execution_id": execution_id,
                    "level": level,
                    "namespace": namespace,
                    "message": message,
                    "data": data or {},
                },
                headers=headers,
            )
    except httpx.RequestError:
        return False
    if r.status_code >= 400:
        return False
    try:
        resp = r.json() if r.content else {"ok": True}
    except ValueError:
        resp = {"ok": True}
    return bool(resp.get("ok", True))


async def ask_via_proxy(
    execution_id: str,
    prompt: str,
    metadata: Dict[str, Any] | None = None,
    *,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> Dict[str, Any]:
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/human/prompts"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
        headers["Authorization"] = f"Bearer {tok}"
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url,
                json={
                    "execution_id": execution_id,
                    "prompt": {"text": prompt},
                    "metadata": metadata or {},
                },
                headers=headers,
            )
    except httpx.RequestError:
        return {"error": "request_failed"}
    if r.status_code >= 400:
        return {"error": r.text}
    try:
        return r.json() if r.content else {"error": "invalid_response"}
    except ValueError:
        return {"error": "invalid_response"}


async def notify_via_proxy(
    execution_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    *,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> bool:
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/session/by-run/{quote(execution_id, safe='')}/notify"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
        headers["Authorization"] = f"Bearer {tok}"
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url, json={"method": method, "params": params or {}}, headers=headers
            )
    except httpx.RequestError:
        return False
    if r.status_code >= 400:
        return False
    try:
        resp = r.json() if r.content else {"ok": True}
    except ValueError:
        resp = {"ok": True}
    return bool(resp.get("ok", True))


async def _request_via_proxy_impl(
    execution_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    *,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
    make_async_call: Optional[bool] = None,
    signal_name: Optional[str] = None,
) -> Dict[str, Any] | None:
    """
    Relay a server->client request via the gateway.

    - If make_async_call is falsy/None: perform synchronous HTTP RPC and return the JSON result.
    - If make_async_call is True: trigger an async request on the server that will signal the
      workflow with the result, then return None (the workflow should wait on signal_name).
    """
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
        headers["Authorization"] = f"Bearer {tok}"

    if bool(make_async_call):
        # Determine workflow_id from Temporal activity context if not provided
        try:
            from temporalio import activity as _ta  # type: ignore
            if _ta.in_activity():
                wf_id = _ta.info().workflow_id
            else:
                wf_id = None
        except Exception:
            wf_id = None

        if not wf_id:
            # Without workflow_id, we cannot route the signal back to the workflow
            return {"error": "not_in_workflow_or_activity"}

        if not signal_name:
            return {"error": "missing_signal_name"}

        url = f"{base}/internal/session/by-run/{quote(wf_id, safe='')}/{quote(execution_id, safe='')}/async-request"
        # Fire-and-forget style: return immediately after enqueuing on server
        timeout_str = os.environ.get("MCP_GATEWAY_REQUEST_TIMEOUT")
        if timeout_str is None:
            timeout = httpx.Timeout(None)
        else:
            try:
                timeout = float(str(timeout_str).strip())
            except Exception:
                timeout = httpx.Timeout(None)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    url,
                    json={
                        "method": method,
                        "params": params or {},
                        "signal_name": signal_name,
                    },
                    headers=headers,
                )
        except httpx.RequestError:
            return {"error": "request_failed"}
        if r.status_code >= 400:
            return {"error": r.text}
        # No payload is expected for async path beyond ack
        return None

    # Synchronous request path
    url = f"{base}/internal/session/by-run/{quote(execution_id, safe='')}/request"
    # Requests require a response; default to no HTTP timeout.
    # Configure with MCP_GATEWAY_REQUEST_TIMEOUT (seconds). If unset or <= 0, no timeout is applied.
    timeout_str = os.environ.get("MCP_GATEWAY_REQUEST_TIMEOUT")
    timeout_float: float | None
    if timeout_str is None:
        timeout_float = None  # no timeout by default; activity timeouts still apply
    else:
        try:
            timeout_float = float(str(timeout_str).strip())
        except Exception:
            timeout_float = None
    try:
        # If timeout is None, pass a Timeout object with no limits
        if timeout_float is None:
            timeout = httpx.Timeout(None)
        else:
            timeout = timeout_float
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url, json={"method": method, "params": params or {}}, headers=headers
            )
    except httpx.RequestError:
        return {"error": "request_failed"}
    if r.status_code >= 400:
        return {"error": r.text}
    try:
        return r.json() if r.content else {"error": "invalid_response"}
    except ValueError:
        return {"error": "invalid_response"}


# Backward-compatible wrapper accepting positional or keyword args
async def request_via_proxy(*args, **kwargs) -> Dict[str, Any] | None:
    """Backward-compatible wrapper for request_via_proxy.

    Supports both positional (execution_id, method, params) and keyword-only usage,
    and forwards optional async parameters when provided as keywords.
    """
    if args:
        # Extract legacy positional args
        execution_id = args[0] if len(args) > 0 else kwargs.get("execution_id")
        method = args[1] if len(args) > 1 else kwargs.get("method")
        params = args[2] if len(args) > 2 else kwargs.get("params")
        # Remaining arguments must be passed as keywords (gateway_url, gateway_token, make_async_call, signal_name)
        return await _request_via_proxy_impl(
            execution_id=execution_id,
            method=method,
            params=params,
            gateway_url=kwargs.get("gateway_url"),
            gateway_token=kwargs.get("gateway_token"),
            make_async_call=kwargs.get("make_async_call"),
            signal_name=kwargs.get("signal_name"),
        )
    # Pure keyword usage
    return await _request_via_proxy_impl(**kwargs)
