import asyncio
import importlib.util
import httpx
import sys

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mcp_agent.app import MCPApp
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.auth import UserCredentials
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.config import MCPServerSettings, MCPSettings


def run_async(coro):
    """
    Simple helper to run an async coroutine from synchronous code.

    This properly handles the event loop setup in all contexts:
    - Normal application usage
    - Within tests that use pytest-asyncio
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # If we're already in an event loop (like in pytest-asyncio tests)
        if "cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        raise


def load_user_app(script_path: Path | None) -> MCPApp:
    """Import a user script and return an MCPApp instance.

    Resolution order within module globals:
      1) variable named 'app' that is MCPApp
      2) callable 'create_app' or 'get_app' that returns MCPApp
      3) first MCPApp instance found in globals
    """
    if script_path is None:
        raise FileNotFoundError("No script specified")
    script_path = script_path.resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    module_name = script_path.stem
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Cannot load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]

    # 1) app variable
    app_obj = getattr(module, "app", None)
    if isinstance(app_obj, MCPApp):
        return app_obj

    # 2) factory
    for fname in ("create_app", "get_app"):
        fn = getattr(module, fname, None)
        if callable(fn):
            res = fn()
            if isinstance(res, MCPApp):
                return res

    # 3) scan globals
    for val in module.__dict__.values():
        if isinstance(val, MCPApp):
            return val

    raise RuntimeError(
        f"No MCPApp instance found in {script_path}. Define 'app = MCPApp(...)' or a create_app()."
    )


def ensure_mcp_servers(app: MCPApp) -> None:
    """Ensure app.context.config has mcp servers dict initialized."""
    cfg = app.context.config
    if cfg.mcp is None:
        cfg.mcp = MCPSettings()
    if cfg.mcp.servers is None:
        cfg.mcp.servers = {}


def attach_url_servers(app: MCPApp, servers: Dict[str, Dict[str, Any]] | None) -> None:
    """Attach URL-based servers (http/sse/streamable_http) to app config."""
    if not servers:
        return
    ensure_mcp_servers(app)
    for name, desc in servers.items():
        settings = MCPServerSettings(
            transport=desc.get("transport", "http"),
            url=desc.get("url"),
            headers=desc.get("headers"),
        )
        app.context.config.mcp.servers[name] = settings


def attach_stdio_servers(
    app: MCPApp, servers: Dict[str, Dict[str, Any]] | None
) -> None:
    """Attach stdio/npx/uvx servers to app config."""
    if not servers:
        return
    ensure_mcp_servers(app)
    for name, desc in servers.items():
        settings = MCPServerSettings(
            transport="stdio",
            command=desc.get("command"),
            args=desc.get("args", []),
        )
        app.context.config.mcp.servers[name] = settings
