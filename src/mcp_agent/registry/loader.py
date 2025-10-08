import os
from typing import Any, Dict, List, Optional

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
    description="Count of tool discovery errors",
)


def _load_config_from_file(path: str) -> List[Dict[str, Any]]:
    """Load server configuration from a file (JSON or YAML)."""
    with open(path, "r") as f:
        content = f.read()
        
    if path.endswith(".json"):
        import json
        return json.loads(content)
    elif path.endswith(".yaml") or path.endswith(".yml"):
        return yaml.safe_load(content)
    else:
        raise ValueError(f"Unsupported config file format: {path}")


def _load_mcp_transport(server_config: Dict[str, Any]):
    """Load MCP transport from server config."""
    from mcp.client.stdio import StdioServerParameters, stdio_client
    
    command = server_config.get("command")
    args = server_config.get("args", [])
    env = server_config.get("env")
    
    if not command:
        raise ValueError("Server configuration must include 'command'")
    
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )
    
    # Create read/write context for the transport
    read, write = stdio_client(server_params)
    
    # Create a simple object to hold read/write
    class Transport:
        pass
    
    transport = Transport()
    transport.read = read
    transport.write = write
    
    return transport


class ToolRegistryLoader:
    """Loads tool definitions from MCP servers into the registry."""
    
    def __init__(self, store: ToolRegistryStore):
        self.store = store
    
    async def discover_and_register_tools(
        self,
        config_path: Optional[str] = None,
        config_url: Optional[str] = None,
    ) -> tuple[int, List[str]]:
        """Discover tools from configured MCP servers and register them.
        
        Args:
            config_path: Path to local config file
            config_url: URL to remote config file
            
        Returns:
            Tuple of (number of tools registered, list of error messages)
        """
        from mcp.client.session import ClientSession
        
        servers = []
        
        if config_url:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(config_url)
                    response.raise_for_status()
                    servers = yaml.safe_load(response.text)
            except Exception as e:
                error_msg = f"Failed to load config from {config_url}: {e}"
                discovery_errors.add(1, {"error_type": "config_load"})
                return 0, [error_msg]
        elif config_path:
            if not os.path.exists(config_path):
                return 0, [f"Config file not found: {config_path}"]
            
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
