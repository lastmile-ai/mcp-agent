import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml
from contextlib import contextmanager

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
    name="discovery_latency_ms",
    description="Time to discover MCP servers",
    unit="ms",
)
discovery_errors = _meter.create_counter(
    name="discovery_errors",
    description="Errors during server discovery",
)

from mcp_agent.registry.store import RegistryStore


class RegistryLoader:
    """Handles loading and validation of MCP server registry configurations."""

    def __init__(self, store: RegistryStore):
        """Initialize loader with a registry store.

        Args:
            store: The registry store to use for loading configurations
        """
        self.store = store

    async def load_from_file(self, file_path: str) -> Dict[str, Any]:
        """Load registry configuration from a YAML file.

        Args:
            file_path: Path to the YAML configuration file

        Returns:
            Parsed configuration dictionary

        Raises:
            FileNotFoundError: If the file doesn't exist
            yaml.YAMLError: If the file is not valid YAML
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Registry file not found: {file_path}")

        with open(file_path) as f:
            config = yaml.safe_load(f)

        return config or {}

    async def load_from_url(self, url: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Load registry configuration from a URL.

        Args:
            url: URL to fetch the configuration from
            timeout: Request timeout in seconds

        Returns:
            Parsed configuration dictionary

        Raises:
            httpx.HTTPError: If the request fails
            yaml.YAMLError: If the response is not valid YAML
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            config = yaml.safe_load(response.text)

        return config or {}

    async def discover_servers(
        self,
        sources: Optional[List[str]] = None,
        include_defaults: bool = True,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Discover MCP servers from multiple sources.

        Args:
            sources: List of file paths or URLs to load from
            include_defaults: Whether to include default registry sources

        Returns:
            Tuple of (merged configuration, list of errors)
        """
        import time

        start_time = time.time()
        errors: List[str] = []
        configs: List[Dict[str, Any]] = []

        # Load from provided sources
        if sources:
            for source in sources:
                try:
                    if source.startswith(("http://", "https://")):
                        config = await self.load_from_url(source)
                    else:
                        config = await self.load_from_file(source)
                    configs.append(config)
                except Exception as e:
                    error_msg = f"Failed to load from {source}: {str(e)}"
                    errors.append(error_msg)
                    discovery_errors.add(1, {"source": source, "error": str(e)})

        # Merge all configurations
        merged = self._merge_configs(configs)

        # Record telemetry
        elapsed_ms = (time.time() - start_time) * 1000
        discovery_latency_ms.record(elapsed_ms, {"num_sources": len(sources or [])})

        return merged, errors

    def _merge_configs(self, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple configuration dictionaries.

        Later configurations override earlier ones for conflicting keys.

        Args:
            configs: List of configuration dictionaries to merge

        Returns:
            Merged configuration dictionary
        """
        merged: Dict[str, Any] = {"mcpServers": {}}

        for config in configs:
            if "mcpServers" in config:
                merged["mcpServers"].update(config["mcpServers"])

        return merged
