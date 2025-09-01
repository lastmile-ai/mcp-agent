import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, AsyncIterator

from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.mcp.mcp_server_registry import ServerRegistry


@asynccontextmanager
async def _proxy_client(
    server_name: str,
    server_registry: ServerRegistry,
) -> AsyncIterator[Any]:
    async with gen_client(server_name, server_registry) as client:
        yield client


async def log_via_proxy(
    server_registry: ServerRegistry,
    run_id: str,
    level: str,
    namespace: str,
    message: str,
    data: Dict[str, Any] | None = None,
    server_name: str = "basic_agent_server",
) -> bool:
    async with _proxy_client(server_name, server_registry) as client:
        try:
            await client.call_tool(
                "workflows-proxy-log",
                arguments={
                    "run_id": run_id,
                    "level": level,
                    "namespace": namespace,
                    "message": message,
                    "data": data or {},
                },
            )
            return True
        except Exception:
            return False


async def ask_via_proxy(
    server_registry: ServerRegistry,
    run_id: str,
    prompt: str,
    metadata: Dict[str, Any] | None = None,
    server_name: str = "basic_agent_server",
) -> Dict[str, Any]:
    async with _proxy_client(server_name, server_registry) as client:
        try:
            resp = await client.call_tool(
                "workflows-proxy-ask",
                arguments={
                    "run_id": run_id,
                    "prompt": prompt,
                    "metadata": metadata or {},
                },
            )
            sc = getattr(resp, "structuredContent", None)
            if isinstance(sc, dict) and "result" in sc:
                return (
                    sc["result"]
                    if isinstance(sc["result"], dict)
                    else {"result": sc["result"]}
                )
            return {"result": None}
        except Exception as e:
            return {"error": str(e)}
