import asyncio
import importlib.util
import sys

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings, MCPSettings, Settings, get_settings


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


def load_user_app(
    script_path: Path | None, settings_override: Optional[Settings] = None
) -> MCPApp:
    """Import a user script and return an MCPApp instance.

    Resolution order within module globals:
      1) variable named 'app' that is MCPApp
      2) callable 'create_app' or 'get_app' that returns MCPApp
      3) first MCPApp instance found in globals

    Args:
        script_path: Path to the Python script containing the MCPApp
        settings_override: Optional settings to override the app's configuration
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
        if settings_override:
            app_obj._config = settings_override
        return app_obj

    # 2) factory
    for fname in ("create_app", "get_app"):
        fn = getattr(module, fname, None)
        if callable(fn):
            res = fn()
            if isinstance(res, MCPApp):
                if settings_override:
                    res._config = settings_override
                return res

    # 3) scan globals
    for val in module.__dict__.values():
        if isinstance(val, MCPApp):
            if settings_override:
                val._config = settings_override
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


def detect_default_script(explicit: Optional[Path]) -> Path:
    """Choose a default script path.

    Preference order:
      1) explicit value if provided
      2) ./main.py
      3) ./agent.py
    Returns the first existing file; if none exist, returns the first preference path (main.py).
    """
    if explicit:
        return explicit
    cwd = Path.cwd()
    main_candidate = cwd / "main.py"
    agent_candidate = cwd / "agent.py"
    if main_candidate.exists():
        return main_candidate
    if agent_candidate.exists():
        return agent_candidate
    # Fall back to main.py (even if missing) so callers can show a helpful message
    return main_candidate


def select_servers_from_config(
    explicit_servers_csv: Optional[str],
    url_servers: Optional[Dict[str, Dict[str, Any]]],
    stdio_servers: Optional[Dict[str, Dict[str, Any]]],
) -> List[str]:
    """Resolve which servers should be active based on inputs and config.

    - If explicit --servers provided, use those
    - Else, if dynamic URL/stdio servers provided, use their names
    - Else, use all servers from mcp_agent.config.yaml (if present)
    """
    if explicit_servers_csv:
        items = [s.strip() for s in explicit_servers_csv.split(",") if s.strip()]
        return items

    names: List[str] = []
    if url_servers:
        names.extend(list(url_servers.keys()))
    if stdio_servers:
        names.extend(list(stdio_servers.keys()))
    if names:
        return names

    settings = get_settings()
    if settings.mcp and settings.mcp.servers:
        return list(settings.mcp.servers.keys())
    return []


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
