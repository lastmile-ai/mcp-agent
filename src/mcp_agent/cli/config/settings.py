"""Configuration settings for MCP Agent Cloud."""

import os
from pydantic_settings import BaseSettings
from ..secrets.constants import ENV_SECRETS_API_URL, ENV_SECRETS_API_TOKEN, DEFAULT_SECRETS_API_URL


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    This uses Pydantic Settings for environment variable loading.
    """
    # Secrets API settings
    SECRETS_API_URL: str = os.environ.get(ENV_SECRETS_API_URL, DEFAULT_SECRETS_API_URL)
    SECRETS_API_TOKEN: str = os.environ.get(ENV_SECRETS_API_TOKEN, "")
    
    # General settings
    VERBOSE: bool = os.environ.get("MCP_VERBOSE", "false").lower() in ("true", "1", "yes")


# Create a singleton settings instance
settings = Settings()