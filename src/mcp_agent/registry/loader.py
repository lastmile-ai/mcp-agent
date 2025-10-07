import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple
import httpx
import yaml
from contextlib import contextmanager

# Try to import opentelemetry, provide dummy classes if unavailable
try:
    from opentelemetry import metrics
    from opentelemetry.metrics import get_meter
    _meter = get_meter(__name__)
except ImportError:
    # Dummy classes for test collection without opentelemetry
    class _DummyMeter:
        def create_histogram(self, *args, **kwargs):
            return _DummyHistogram()
        def create_counter(self, *args, **kwargs):
            return _DummyCounter()
    
    class _DummyHistogram:
        def record(self, value, attributes=None):
            pass
        @contextmanager
        def time(self):
            yield
    
    class _DummyCounter:
        def add(self, value, attributes=None):
            pass
    
    _meter = _DummyMeter()

# Telemetry
discovery_latency_ms = _meter.create_histogram(
    name="discovery_latency_ms",
    description="Latency of tool discovery probes in milliseconds",
    unit="ms"
)

capabilities_total = _meter.create_counter(
    name="capabilities_total",
    description="Total discovered capabilities by name"
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
        import time
        start_time = time.perf_counter()
        r = await client.get(f"{base_url.rstrip('/')}/.well-known/mcp", timeout=3.0)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        discovery_latency_ms.record(elapsed_ms)
        
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            j = r.json()
            # Accept either root fields or nested under 'mcp'
            meta = j.get("mcp", j)
            version = meta.get("version") or j.get("version")
            caps = meta.get("capabilities") or j.get("capabilities") or {}
            if isinstance(caps, dict):
                for k in caps.keys():
                    capabilities_total.add(1, attributes={"capability": str(k)})
            info.update({"version": version, "capabilities": caps, "well_known": True})
            return True, info
    except Exception:
        pass
    # Fallback to /health
    try:
        import time
        start_time = time.perf_counter()
        r = await client.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        discovery_latency_ms.record(elapsed_ms)
        
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
