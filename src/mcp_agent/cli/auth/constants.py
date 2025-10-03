"""Constants for the MCP Agent auth utilities."""

import os

# Default credentials location (legacy)
DEFAULT_CREDENTIALS_PATH = "~/.mcp-agent/credentials.json"

# Additional locations to search (XDG-compatible and documented path)
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
ALTERNATE_CREDENTIALS_PATHS = [
    os.path.join(XDG_CONFIG_HOME, "mcp-agent", "credentials.json"),
]
