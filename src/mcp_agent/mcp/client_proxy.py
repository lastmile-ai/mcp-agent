from typing import Any, Dict, Optional

import os
import httpx

from mcp_agent.mcp.mcp_server_registry import ServerRegistry


def _resolve_gateway_url(
    server_registry: Optional[ServerRegistry] = None,
    server_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
) -> str:
    # Highest precedence: explicit override
    if gateway_url:
        return gateway_url.rstrip("/")

    # Next: environment variable
    env_url = os.environ.get("MCP_GATEWAY_URL")
    if env_url:
        return env_url.rstrip("/")

    # Next: a registry entry (if provided)
    if server_registry and server_name:
        cfg = server_registry.get_server_context(server_name)
        if cfg and getattr(cfg, "url", None):
            return cfg.url.rstrip("/")

    # Fallback: default local server
    return "http://127.0.0.1:8000"


async def log_via_proxy(
    server_registry: Optional[ServerRegistry],
    execution_id: str,
    level: str,
    namespace: str,
    message: str,
    data: Dict[str, Any] | None = None,
    *,
    server_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> bool:
    base = _resolve_gateway_url(server_registry, server_name, gateway_url)
    url = f"{base}/internal/workflows/log"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))
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
        if r.status_code >= 400:
            return False
        resp = r.json()
        return bool(resp.get("ok", False))


async def ask_via_proxy(
    server_registry: Optional[ServerRegistry],
    execution_id: str,
    prompt: str,
    metadata: Dict[str, Any] | None = None,
    *,
    server_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> Dict[str, Any]:
    base = _resolve_gateway_url(server_registry, server_name, gateway_url)
    url = f"{base}/internal/human/prompts"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))
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
        if r.status_code >= 400:
            return {"error": r.text}
        return r.json()


async def notify_via_proxy(
    server_registry: Optional[ServerRegistry],
    execution_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    *,
    server_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> bool:
    base = _resolve_gateway_url(server_registry, server_name, gateway_url)
    url = f"{base}/internal/session/by-run/{execution_id}/notify"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "10"))

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            url, json={"method": method, "params": params or {}}, headers=headers
        )
        if r.status_code >= 400:
            return False
        resp = r.json() if r.content else {"ok": True}
        return bool(resp.get("ok", True))


async def request_via_proxy(
    server_registry: Optional[ServerRegistry],
    execution_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    *,
    server_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
) -> Dict[str, Any]:
    base = _resolve_gateway_url(server_registry, server_name, gateway_url)
    url = f"{base}/internal/session/by-run/{execution_id}/request"
    headers: Dict[str, str] = {}
    tok = gateway_token or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        headers["X-MCP-Gateway-Token"] = tok
    timeout = float(os.environ.get("MCP_GATEWAY_TIMEOUT", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            url, json={"method": method, "params": params or {}}, headers=headers
        )
        if r.status_code >= 400:
            return {"error": r.text}
        return r.json()
