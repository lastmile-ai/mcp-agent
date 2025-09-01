from typing import Any, Dict

import httpx

from mcp_agent.mcp.mcp_server_registry import ServerRegistry


def _resolve_gateway_url(server_registry: ServerRegistry, server_name: str) -> str:
    cfg = server_registry.get_server_context(server_name)
    # Prefer streamable-http if configured; else assume localhost: settings in examples
    if cfg and getattr(cfg, "url", None):
        return cfg.url.rstrip("/")
    host = "http://{}:{}".format("127.0.0.1", 8000)
    return host


async def log_via_proxy(
    server_registry: ServerRegistry,
    run_id: str,
    level: str,
    namespace: str,
    message: str,
    data: Dict[str, Any] | None = None,
    server_name: str = "basic_agent_server",
) -> bool:
    base = _resolve_gateway_url(server_registry, server_name)
    url = f"{base}/internal/workflows/log"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            url,
            json={
                "run_id": run_id,
                "level": level,
                "namespace": namespace,
                "message": message,
                "data": data or {},
            },
        )
        if r.status_code >= 400:
            return False
        resp = r.json()
        return bool(resp.get("ok", False))


async def ask_via_proxy(
    server_registry: ServerRegistry,
    run_id: str,
    prompt: str,
    metadata: Dict[str, Any] | None = None,
    server_name: str = "basic_agent_server",
) -> Dict[str, Any]:
    base = _resolve_gateway_url(server_registry, server_name)
    url = f"{base}/internal/human/prompts"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            url,
            json={
                "run_id": run_id,
                "prompt": {"text": prompt},
                "metadata": metadata or {},
            },
        )
        if r.status_code >= 400:
            return {"error": r.text}
        return r.json()
