"""Configuration settings for MCP Agent Cloud."""

import os
from pydantic_settings import BaseSettings
from ..secrets.constants import SecretsMode


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    This uses Pydantic Settings for environment variable loading.
    """
    # Secrets mode
    SECRETS_MODE: str = os.environ.get("MCP_SECRETS_MODE", SecretsMode.API)
    
    # Vault settings
    VAULT_ADDR: str = os.environ.get("VAULT_ADDR", "http://localhost:8200")
    VAULT_TOKEN: str = os.environ.get("VAULT_TOKEN", "")
    
    # Secrets API settings
    SECRETS_API_URL: str = os.environ.get("MCP_SECRETS_API_URL", "http://localhost:3000/api/v1")
    SECRETS_API_TOKEN: str = os.environ.get("MCP_SECRETS_API_TOKEN", "")
    
    # General settings
    VERBOSE: bool = os.environ.get("MCP_VERBOSE", "false").lower() in ("true", "1", "yes")


# Create a singleton settings instance
settings = Settings()