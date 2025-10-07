import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml
from prometheus_client import Histogram, Counter

# Telemetry
discovery_latency_ms = Histogram(
    "discovery_latency_ms",
    "Latency of tool discovery probes in milliseconds",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)
capabilities_total = Counter(
    "capabilities_total",
    "Total discovered capabilities by name",
    ["capability"],
)

DEFAULT_TOOLS_YAML = os.getenv("TOOLS_YAML_PATH", "tools/tools.yaml")


def load_tools_yaml(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse tools.yaml. Returns list of entries with at least name and base_url."""
    p = path or DEFAULT_TOOLS_YAML
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get("tools") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        base = it.get("base_url") or it.get("baseURL")
        version = it.get("version")
        if not name or not base:
            continue
        out.append({"name": str(name), "base_url": str(base), "version": version})
    return out


async def _probe_one(client: httpx.AsyncClient, base_url: str) -> Tuple[bool, Dict[str, Any]]:
    """Probe /.well-known/mcp then /health. Returns (alive, info)."""
    info: Dict[str, Any] = {}
    # Try well-known MCP first
    try:
        with discovery_latency_ms.time():
            r = await client.get(f"{base_url.rstrip('/')}/.well-known/mcp", timeout=3.0)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            j = r.json()
            # Accept either root fields or nested under 'mcp'
            meta = j.get("mcp", j)
            version = meta.get("version") or j.get("version")
            caps = meta.get("capabilities") or j.get("capabilities") or {}
            if isinstance(caps, dict):
                for k in caps.keys():
                    capabilities_total.labels(capability=str(k)).inc()
            info.update({"version": version, "capabilities": caps, "well_known": True})
            return True, info
    except Exception:
        pass
    # Fallback to /health
    try:
        with discovery_latency_ms.time():
            r = await client.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
        if r.status_code == 200:
            info.update({"health": True})
            return True, info
    except Exception:
        pass
    return False, info


async def discover(entries: List[Dict[str, Any]], retries: int = 2, backoff_ms: int = 50) -> List[Dict[str, Any]]:
    """Probe all entries with limited retries. Returns registry records."""
    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for it in entries:
            name = it["name"]
            base = it["base_url"]
            version = it.get("version")
            info: Dict[str, Any] = {}
            alive = False
            attempt = 0
            while attempt <= retries and not alive:
                alive, info = await _probe_one(client, base)
                if not alive:
                    await asyncio.sleep(backoff_ms / 1000)
                attempt += 1
            record = {
                "name": name,
                "base_url": base,
                "version": info.get("version", version),
                "capabilities": info.get("capabilities", {}),
                "alive": bool(alive),
                "well_known": bool(info.get("well_known", False)),
            }
            out.append(record)
    return out
