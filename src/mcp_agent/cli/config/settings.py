"""Configuration settings for MCP Agent Cloud."""

import os

from pydantic_settings import BaseSettings

from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    DEFAULT_CACHE_DIR,
    ENV_API_BASE_URL,
    ENV_API_KEY,
)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    This uses Pydantic Settings for environment variable loading.
    """

    # API settings
    API_BASE_URL: str = os.environ.get(ENV_API_BASE_URL, DEFAULT_API_BASE_URL)
    API_KEY: str = os.environ.get(ENV_API_KEY, "")

    # Cache dir for deployment
    DEPLOYMENT_CACHE_DIR: str = os.environ.get(
        "MCP_DEPLOYMENT_CACHE_DIR", DEFAULT_CACHE_DIR
    )

    # General settings
    VERBOSE: bool = os.environ.get("MCP_VERBOSE", "false").lower() in (
        "true",
        "1",
        "yes",
    )


# Create a singleton settings instance
settings = Settings()
