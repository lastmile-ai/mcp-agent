import os
from typing import Any, Dict, List, Optional, Tuple
import httpx
import yaml
from contextlib import contextmanager
from mcp_agent.registry.store import ToolRegistryStore

# Try to import opentelemetry, provide dummy classes if unavailable
try:
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
    name="mcp_agent.discovery.latency_ms",
    unit="ms",
    description="Latency of discovery operations in milliseconds"
)

discovery_failed_count = _meter.create_counter(
    name="mcp_agent.discovery.failed_count",
    unit="1",
    description="Number of failed discovery attempts"
)

def load_tools_yaml(tools_yaml_path: Optional[str] = None) -> List[Dict[str, Any]]:
    path = tools_yaml_path or os.getenv("TOOLS_YAML", "tools.yaml")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []

class RegistryLoader:
    def __init__(self, store: Optional[ToolRegistryStore] = None):
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=float(os.getenv("MCP_CONNECT_TIMEOUT_SEC", "5.0")),
                read=float(os.getenv("MCP_READ_TIMEOUT_SEC", "10.0"))
            ),
            follow_redirects=True
        )
        self.store = store or ToolRegistryStore()
    
    async def discover_tool(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tool_name = entry.get("name", "")
        tool_type = entry.get("type", "stdio")
        
        if tool_type == "sse":
            url = entry.get("url")
            if not url:
                return None
            try:
                with discovery_latency_ms.time():
                    response = await self.http_client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    return {
                        "name": tool_name,
                        "type": tool_type,
                        "url": url,
                        "metadata": data
                    }
            except Exception as e:
                discovery_failed_count.add(1, attributes={"tool": tool_name, "error": str(e)})
                return None
        else:
            # For stdio and other types, just return the entry as-is
            return entry
    
    async def close(self):
        await self.http_client.aclose()

async def discover(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    loader = RegistryLoader()
    try:
        discovered = []
        for entry in entries:
            tool = await loader.discover_tool(entry)
            if tool:
                discovered.append(tool)
        return discovered
    finally:
        await loader.close()
