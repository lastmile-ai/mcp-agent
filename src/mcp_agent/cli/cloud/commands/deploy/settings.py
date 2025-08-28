"""Deployment-specific URL settings for MCP Agent Cloud."""

import os

from pydantic_settings import BaseSettings

from .constants import DEFAULT_DEPLOYMENTS_UPLOAD_API_BASE_URL


class DeploymentURLSettings(BaseSettings):
    """
    Deployment-specific URL settings loaded from environment variables.

    Only the base URL is configurable via environment variable.
    All other URLs are constructed from the base URL.
    """

    # Base URL for deployments upload API (configurable)
    DEPLOYMENTS_UPLOAD_API_BASE_URL: str = os.environ.get(
        "MCP_DEPLOYMENTS_UPLOAD_API_BASE_URL", DEFAULT_DEPLOYMENTS_UPLOAD_API_BASE_URL
    )

    @property
    def wrangler_auth_domain(self) -> str:
        """Construct Wrangler auth domain from base URL."""
        return f"{self.DEPLOYMENTS_UPLOAD_API_BASE_URL}/auth"

    @property
    def wrangler_auth_url(self) -> str:
        """Construct Wrangler auth URL from base URL."""
        return f"{self.DEPLOYMENTS_UPLOAD_API_BASE_URL}/auth/oauth2/auth"

    @property
    def cloudflare_api_base_url(self) -> str:
        """Construct Cloudflare API base URL from base URL."""
        return f"{self.DEPLOYMENTS_UPLOAD_API_BASE_URL}/api"


# Create a singleton settings instance
deployment_settings = DeploymentURLSettings()
