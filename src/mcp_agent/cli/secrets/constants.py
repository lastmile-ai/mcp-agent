"""Constants for the MCP Agent Cloud Secrets module."""

from enum import Enum


class SecretType(Enum):
    """Enum representing the type of secret."""
    DEVELOPER = "developer"
    USER = "user"


# Handle prefixes
DEV_HANDLE_PREFIX = "mcpac_dev_"
USR_HANDLE_PREFIX = "mcpac_usr_"

# Environment variable names
ENV_SECRETS_API_URL = "MCP_SECRETS_API_URL"
ENV_SECRETS_API_TOKEN = "MCP_SECRETS_API_TOKEN"

# Default values
DEFAULT_SECRETS_API_URL = "http://localhost:3000/api"