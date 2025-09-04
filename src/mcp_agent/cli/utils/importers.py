"""
Import helpers to convert external client configs (mcp.json, etc.) into
MCPServerSettings entries usable by mcp-agent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import json

from mcp_agent.config import MCPServerSettings


def _detect_transport(obj: dict) -> str:
    url = obj.get("url")
    if url:
        # Determine sse vs http by path suffix
        return "sse" if str(url).rstrip("/").endswith("/sse") else "http"
    return obj.get("transport") or "stdio"


def _to_settings(obj: dict) -> MCPServerSettings:
    transport = _detect_transport(obj)
    if transport == "stdio":
        return MCPServerSettings(
            transport="stdio",
            command=obj.get("command"),
            args=obj.get("args") or [],
            env=obj.get("env") or None,
        )
    else:
        return MCPServerSettings(
            transport=transport,
            url=obj.get("url"),
            headers=obj.get("headers") or None,
        )


def import_servers_from_mcp_json(path: Path) -> Dict[str, MCPServerSettings]:
    """
    Parse a cursor/vscode style mcp.json into a mapping of name -> MCPServerSettings.
    Supports a variety of simple schemas:
      - { "mcp": { "servers": { name: { ... } } } }
      - { name: { ... } }
      - [ { "name": str, ... }, ... ]
    """
    text = path.read_text(encoding="utf-8")
    data: Any = json.loads(text)
    servers: Dict[str, MCPServerSettings] = {}

    # mcp.servers mapping
    if isinstance(data, dict) and "mcp" in data and isinstance(data["mcp"], dict):
        mcp = data["mcp"]
        s_map = mcp.get("servers") or {}
        if isinstance(s_map, dict):
            for name, cfg in s_map.items():
                if isinstance(cfg, dict):
                    servers[str(name)] = _to_settings(cfg)
            return servers

    # direct mapping name -> cfg
    if isinstance(data, dict):
        # Filter out non-server-like keys
        for name, cfg in data.items():
            if isinstance(cfg, dict) and (
                "command" in cfg or "url" in cfg or "transport" in cfg
            ):
                servers[str(name)] = _to_settings(cfg)
        if servers:
            return servers

    # list of servers with name
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item:
                servers[str(item["name"])] = _to_settings(item)
        if servers:
            return servers

    # No recognized structure
    return {}
