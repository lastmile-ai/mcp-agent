from typing import Any, Dict, Optional

from .base import BaseAdapter

WELL_KNOWN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "capabilities": {"type": "object"},
    },
    "required": ["name", "version"],
}

class GithubMCPAdapter(BaseAdapter):
    def __init__(self, base_url: str):
        super().__init__("github-mcp-server", base_url, schema=WELL_KNOWN_SCHEMA)

    def describe(self) -> Dict[str, Any]:
        return self.get("/.well-known/mcp")
