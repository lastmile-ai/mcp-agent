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
    name="mcp_agent_discovery_latency_ms",
    description="Time to perform tool discovery in milliseconds",
    unit="ms",
)

discovery_errors = _meter.create_counter(
    name="mcp_agent_discovery_errors",
    description="Count of discovery errors",
    unit="1",
)


def _load_mcp_transport(config: Dict[str, Any]) -> Any:
    """Load and initialize MCP transport from config."""
    transport_type = config.get("transportType")
    args = config.get("args", {})

    if transport_type == "http":
        from mcp import OKTransport
        return OKTransport(
            url=args.get("url"),
            timeout=httpx.Timeout(
                connect=float(os.getenv("MCP_CONNECT_TIMEOUT_SEC", "5.0")),
                read=float(os.getenv("MCP_READ_TIMEOUT_SEC", "10.0")),
                write=float(os.getenv("MCP_WRITE_TIMEOUT_SEC", "10.0")),
                pool=float(os.getenv("MCP_POOL_TIMEOUT_SEC", "5.0"))
            ),
        )
    elif transport_type == "stdio":
        from mcp import StdioTransport
        return StdioTransport(
            command=args.get("command"),
            args=args.get("args", []),
            env=args.get("env"),
        )
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")


def _load_config_from_file(config_path: str) -> List[Dict[str, Any]]:
    """Load MCP configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        List of server configurations
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Handle both list and dict formats
    if isinstance(config, list):
        return config
    elif isinstance(config, dict):
        # If it's a dict with 'servers' key, return the servers list
        if 'servers' in config:
            return config['servers']
        # Otherwise, treat it as a single server config
        return [config]
    else:
        raise ValueError(f"Invalid config format: {type(config)}")


class ToolRegistryLoader:
    """Loader for discovering and loading tools from MCP servers."""

    def __init__(self, store: ToolRegistryStore):
        """Initialize the loader with a store.
        
        Args:
            store: ToolRegistryStore to register discovered tools
        """
        self.store = store

    async def discover_and_load(
        self,
        config_path: Optional[str] = None,
        servers: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[int, List[str]]:
        """Discover and load tools from MCP servers.
        
        Args:
            config_path: Path to YAML config file (optional)
            servers: List of server configurations (optional)
            
        Returns:
            Tuple of (number of tools loaded, list of error messages)
        """
        import asyncio
        from mcp import ClientSession
        
        # Load config from file if provided
        if config_path:
            try:
                servers = _load_config_from_file(config_path)
            except Exception as e:
                error_msg = f"Failed to load config from {config_path}: {e}"
                discovery_errors.add(1, {"error_type": "config_load"})
                return 0, [error_msg]
        
        if not servers:
            return 0, ["No servers configured"]
        
        total_tools = 0
        errors = []
        
        for server_config in servers:
            server_name = server_config.get("name", "unknown")
            
            try:
                with discovery_latency_ms.time():
                    # Load transport
                    transport = _load_mcp_transport(server_config)
                    
                    # Create client session and discover tools
                    async with ClientSession(
                        read=transport.read,
                        write=transport.write,
                    ) as session:
                        # Initialize the session
                        await session.initialize()
                        
                        # List available tools
                        tools_response = await session.list_tools()
                        
                        # Register each tool
                        for tool in tools_response.tools:
                            self.store.register_tool(
                                name=tool.name,
                                description=tool.description or "",
                                input_schema=tool.inputSchema,
                                server=server_name,
                            )
                            total_tools += 1
                            
            except Exception as e:
                error_msg = f"Failed to load tools from {server_name}: {e}"
                errors.append(error_msg)
                discovery_errors.add(1, {"error_type": "discovery", "server": server_name})
                
        return total_tools, errors
