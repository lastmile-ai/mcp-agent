"""Core constants for MCP Agent Cloud.

This module contains constants that are used throughout the MCP Agent Cloud codebase.
Centralizing these constants helps prevent circular imports and provides a single
source of truth for values that are referenced by multiple modules.
"""

import re
from enum import Enum

# File names and patterns
MCP_CONFIG_FILENAME = "mcp_agent.config.yaml"
MCP_CONFIGURED_SECRETS_FILENAME = "mcp_agent.configured.secrets.yaml"
MCP_DEPLOYED_SECRETS_FILENAME = "mcp_agent.deployed.secrets.yaml"
MCP_SECRETS_FILENAME = "mcp_agent.secrets.yaml"

# Cache and deployment settings
DEFAULT_CACHE_DIR = (
    "~/.mcp_agent/cloud"  # Moved from commands/deploy/constants.py
)

# Environment variable names
ENV_API_BASE_URL = "MCP_API_BASE_URL"  # Moved from secrets/constants.py
ENV_API_KEY = "MCP_API_KEY"  # Moved from secrets/constants.py
ENV_VERBOSE = "MCP_VERBOSE"  # Moved from settings.py usage

# API defaults
DEFAULT_API_BASE_URL = "https://mcp-agent-cloud-internal.lastmileai.dev/api"  # Moved from secrets/constants.py

# Secret types (string constants)
SECRET_TYPE_DEVELOPER = "dev"  # Value from SecretType.DEVELOPER
SECRET_TYPE_USER = "usr"  # Value from SecretType.USER


# SecretType Enum for backwards compatibility
class SecretType(Enum):
    """Enum representing the type of secret."""

    DEVELOPER = SECRET_TYPE_DEVELOPER  # Secrets known at deploy time
    USER = (
        SECRET_TYPE_USER  # Secrets collected from end-users at configure time
    )


# UUID patterns for secret handles
UUID_PREFIX = "mcpac_sc_"  # Prefix for secret IDs to identify entity type
# Strict pattern for UUID validation - only standard UUID format with prefix
UUID_PATTERN = f"^{UUID_PREFIX}[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$"
# Use the strict pattern for all validation
SECRET_ID_PATTERN = re.compile(UUID_PATTERN)
