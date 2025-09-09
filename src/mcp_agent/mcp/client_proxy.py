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


async def log_via_proxy(*args, **kwargs) -> bool:
    """Backward-compatible wrapper.

    Accepts either:
      - legacy: (server_registry, execution_id, level, namespace, message, data=None, *, gateway_url=None, gateway_token=None)
      - new: (execution_id, level, namespace, message, data=None, *, gateway_url=None, gateway_token=None)
    """
    if args and (args[0] is None or not isinstance(args[0], str)):
        args = args[1:]
    execution_id, level, namespace, message, *rest = args
    data = rest[0] if rest else None
    gateway_url = kwargs.get("gateway_url")
    gateway_token = kwargs.get("gateway_token")
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/workflows/log"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
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


async def ask_via_proxy(*args, **kwargs) -> Dict[str, Any]:
    # legacy: (server_registry, execution_id, prompt, metadata=None, ...)
    if args and (args[0] is None or not isinstance(args[0], str)):
        args = args[1:]
    execution_id, prompt, *rest = args
    metadata = rest[0] if rest else None
    gateway_url = kwargs.get("gateway_url")
    gateway_token = kwargs.get("gateway_token")
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/human/prompts"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
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


async def notify_via_proxy(*args, **kwargs) -> bool:
    # legacy: (server_registry, execution_id, method, params=None, ...)
    if args and (args[0] is None or not isinstance(args[0], str)):
        args = args[1:]
    execution_id, method, *rest = args
    params = rest[0] if rest else None
    gateway_url = kwargs.get("gateway_url")
    gateway_token = kwargs.get("gateway_token")
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/session/by-run/{quote(execution_id, safe='')}/notify"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
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


async def request_via_proxy(*args, **kwargs) -> Dict[str, Any]:
    # legacy: (server_registry, execution_id, method, params=None, ...)
    if args and (args[0] is None or not isinstance(args[0], str)):
        args = args[1:]
    execution_id, method, *rest = args
    params = rest[0] if rest else None
    gateway_url = kwargs.get("gateway_url")
    gateway_token = kwargs.get("gateway_token")
    base = _resolve_gateway_url(gateway_url=gateway_url, context_gateway_url=None)
    url = f"{base}/internal/session/by-run/{quote(execution_id, safe='')}/request"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "20"))
    try:
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
