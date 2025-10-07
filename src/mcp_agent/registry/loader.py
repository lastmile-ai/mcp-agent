import os
from typing import Any, Dict, List, Optional, Tuple
import httpx
import yaml
from contextlib import contextmanager
from mcp_agent.registry.store import RegistryStore

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
    "registry.discovery.latency_ms",
    description="Time to discover and load registry configurations",
    unit="ms"
)
discovery_error_count = _meter.create_counter(
    "registry.discovery.errors",
    description="Number of errors during registry discovery"
)


class RegistryLoader:
    """Loads MCP server configurations from various sources."""
    
    def __init__(self, store: Optional[RegistryStore] = None):
        """Initialize registry loader.
        
        Args:
            store: Optional registry store for testing. If None, creates default store.
        """
        import time
        self.start_time = time.time()
        self.store = store or RegistryStore()
    
    def discover_configs(self, sources: Optional[List[str]] = None) -> Tuple[Dict[str, Any], List[str]]:
        """Discover and load configurations from multiple sources.
        
        Args:
            sources: Optional list of configuration file paths. If None, uses default discovery.
        
        Returns:
            Tuple of (merged_config, error_messages)
        """
        import time
        start_time = time.time()
        
        configs = []
        errors = []
        
        # Default discovery if no sources specified
        if sources is None:
            sources = self._default_sources()
        
        # Load each source
        for source in sources:
            try:
                config = self._load_source(source)
                if config:
                    configs.append(config)
            except Exception as e:
                error_msg = f"Failed to load {source}: {str(e)}"
                errors.append(error_msg)
                discovery_error_count.add(1, {"source": source})
        
        # Merge all configs
        merged = self._merge_configs(configs)
        
        # Record discovery latency
        elapsed_ms = (time.time() - start_time) * 1000
        discovery_latency_ms.record(elapsed_ms, {"num_sources": len(sources or [])})
        
        return merged, errors
    
    def _default_sources(self) -> List[str]:
        """Get default configuration sources.
        
        Returns:
            List of default configuration file paths
        """
        sources = []
        
        # User config
        home = os.path.expanduser("~")
        user_config = os.path.join(home, ".mcp", "config.json")
        if os.path.exists(user_config):
            sources.append(user_config)
        
        # System config
        system_config = "/etc/mcp/config.json"
        if os.path.exists(system_config):
            sources.append(system_config)
        
        # Registry store
        try:
            registry_configs = self.store.list_configs()
            sources.extend(registry_configs)
        except Exception:
            pass  # Registry store not available
        
        return sources
    
    def _load_source(self, source: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a single source.
        
        Args:
            source: Configuration source (file path or URL)
        
        Returns:
            Configuration dictionary or None if source is empty
        """
        if source.startswith("http://") or source.startswith("https://"):
            return self._load_url(source)
        else:
            return self._load_file(source)
    
    def _load_file(self, path: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a file.
        
        Args:
            path: File path to load
        
        Returns:
            Configuration dictionary or None if file is empty
        """
        with open(path, 'r') as f:
            content = f.read()
            if not content.strip():
                return None
            
            if path.endswith('.json'):
                import json
                return json.loads(content)
            elif path.endswith(('.yml', '.yaml')):
                return yaml.safe_load(content)
            else:
                raise ValueError(f"Unsupported file format: {path}")
    
    def _load_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a URL.
        
        Args:
            url: URL to load configuration from
        
        Returns:
            Configuration dictionary or None if response is empty
        """
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        
        content = response.text
        if not content.strip():
            return None
        
        content_type = response.headers.get('content-type', '')
        if 'json' in content_type:
            return response.json()
        elif 'yaml' in content_type or 'yml' in content_type:
            return yaml.safe_load(content)
        else:
            # Try to detect format from content
            try:
                return response.json()
            except Exception:
                return yaml.safe_load(content)
    
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
