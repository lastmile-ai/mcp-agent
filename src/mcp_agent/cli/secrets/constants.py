"""Constants for the MCP Agent Cloud Secrets module."""

from enum import Enum


class SecretType(Enum):
    """Enum representing the type of secret."""
    DEVELOPER = "developer"
    USER = "user"


class SecretsMode(str, Enum):
    """Mode for handling secrets."""
    DIRECT_VAULT = "direct_vault"
    API = "api"


# Vault paths
VAULT_SECRETS_PATH = "mcp/mvp0_secrets"  # Path within the secret mount

# Handle prefixes
DEV_HANDLE_PREFIX = "mcpac_dev_"
USR_HANDLE_PREFIX = "mcpac_usr_"
MVP0_DEV_HANDLE_PREFIX = "mcpac_mvp0_dev_"
MVP0_USR_HANDLE_PREFIX = "mcpac_mvp0_usr_"

# Environment variable names
ENV_SECRETS_MODE = "MCP_SECRETS_MODE"
ENV_VAULT_ADDR = "VAULT_ADDR"
ENV_VAULT_TOKEN = "VAULT_TOKEN"
ENV_SECRETS_API_URL = "MCP_SECRETS_API_URL"
ENV_SECRETS_API_TOKEN = "MCP_SECRETS_API_TOKEN"

# Default values
DEFAULT_VAULT_ADDR = "http://localhost:8200"
DEFAULT_SECRETS_API_URL = "http://localhost:3000/api/v1"