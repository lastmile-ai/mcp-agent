import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import httpx
import yaml

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


__all__ = ['discover', 'load_tools_yaml']


class ToolRegistryLoader:
    """
    A class responsible for loading and registering MCP tools from various sources.
    This class handles:
    - Discovering tools via .well-known/mcp.json
    - Loading tool configurations from files
    - Registering tools in the ToolRegistryStore
    """
    def __init__(self, store: Optional[ToolRegistryStore] = None):
        """Initialize the ToolRegistryLoader.
        Args:
            store: Optional ToolRegistryStore instance. If not provided, creates a new one.
        """
        self.store = store or ToolRegistryStore()
        self._discovery_duration_hist = _meter.create_histogram(
            name="mcp_agent.registry.loader.discovery.duration",
            unit="ms",
            description="Discovery request duration in milliseconds"
        )
        self._discovery_counter = _meter.create_counter(
            name="mcp_agent.registry.loader.discovery.count",
            unit="1",
            description="Number of discovery requests"
        )

    async def discover_and_register_tools(
        self,
        entries: List[Dict[str, Any]],
        timeout: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Discover tools from a list of server entries and register them.
        Args:
            entries: List of server entries, each containing 'name' and 'base_url'.
            timeout: Request timeout in seconds (default: 5.0).
        Returns:
            List of discovery results for each entry.
        """
        results = await discover(entries, timeout=timeout)

        # Register discovered tools
        for entry, result in zip(entries, results):
            if result.get("alive") and result.get("capabilities"):
                # Extract tools from capabilities if available
                capabilities = result.get("capabilities", {})
                tools = capabilities.get("tools", [])

                for tool in tools:
                    self.store.register_tool(
                        name=tool.get("name"),
                        server_name=entry["name"],
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema", {}),
                        metadata={"base_url": entry["base_url"]}
                    )

        return results


def _load_config_from_file(path: str) -> Dict[str, Any]:
    """Load configuration from a YAML file.
    Args:
        path: Path to the YAML configuration file.
    Returns:
        Parsed configuration as a dictionary.
    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, 'r') as f:
        return yaml.safe_load(f)


def _load_mcp_transport(base_url: str) -> Optional[Dict[str, Any]]:
    """Load MCP transport configuration from a base URL.
    Args:
        base_url: Base URL of the MCP server.
    Returns:
        Transport configuration dictionary or None if unavailable.
    """
    # Placeholder implementation
    return {"type": "http", "base_url": base_url}


async def discover(
    entries: List[Dict[str, Any]],
    timeout: float = 2.0
) -> List[Dict[str, Any]]:
    """Probe each registry entry for /.well-known/mcp and /health.
    Args:
        entries: List of {name, base_url}
        timeout: per-request timeout in seconds
    Returns:
        List of entries augmented with:
          - alive: bool
          - well_known: bool
          - capabilities: dict
    """
    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for e in entries:
            base = e.get('base_url') or ''
            info = dict(e)
            info.setdefault('capabilities', {})
            info['alive'] = False
            info['well_known'] = False
            try:
                wk = await client.get(f"{base}/.well-known/mcp")
                if wk.status_code == 200:
                    info['well_known'] = True
                    try:
                        data = wk.json()
                        if isinstance(data, dict):
                            caps = data.get('capabilities') or {}
                            if isinstance(caps, dict):
                                info['capabilities'] = caps
                    except Exception:
                        pass
            except Exception:
                # leave as defaults
                pass
            try:
                h = await client.get(f"{base}/health")
                if h.status_code == 200:
                    try:
                        hj = h.json()
                        ok = hj.get('ok') if isinstance(hj, dict) else None
                        info['alive'] = bool(ok) if ok is not None else True
                    except Exception:
                        info['alive'] = True
            except Exception:
                info['alive'] = False
            out.append(info)
    return out


def load_tools_yaml(file_path: str) -> Dict[str, Any]:
    """Load a tools.yaml and return the parsed mapping.
    Returns an empty dict if YAML content is empty.
    Raises FileNotFoundError if the path does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Tools YAML file not found: {file_path}")
    with open(file_path, 'r') as f:
        content = yaml.safe_load(f)
    return content or {}
