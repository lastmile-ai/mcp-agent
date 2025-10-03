"""Mock Client for dry run mode.

This module provides a mock implementation of the MCPAppClient interface
that generates fake app data instead of making real API calls.
"""

import datetime
import uuid
from typing import Any, Dict, List, Optional

from .api_client import (
    MCPApp,
    MCPAppConfiguration,
)

MOCK_APP_NAME = "Test App"
MOCK_APP_ID = "app_aece3598-d229-46d8-83fb-8c61ca7cd435"
MOCK_APP_CONFIG_ID = "apcnf_55b256a8-3077-431c-9211-b931633bf4c0"
MOCK_APP_SERVER_URL = "https://mockappaece3598.deployments.mcp-agent.com"


class MockMCPAppClient:
    """Mock client that generates fake app data for dry run mode."""

    def __init__(self, api_url: str = "http://mock-api", api_key: str = "mock-key"):
        """Initialize the mock client.

        Args:
            api_url: Mock API URL (ignored)
            api_key: Mock API key
        """
        self.api_url = api_url
        self.api_key = api_key
        self._createdApps: Dict[str, Dict[str, MCPApp]] = {}

    async def get_app_id_by_name(self, name: str) -> Optional[str]:
        """Get a mock app ID by name. Deterministic for MOCK_APP_NAME name.

        Args:
            name: The name of the MCP App

        Returns:
            Optional[str]: The MOCK_APP_ID for MOCK_APP_NAME, or None for other names.
        """
        return MOCK_APP_ID if name == MOCK_APP_NAME else None

    async def get_app(
        self, app_id: Optional[str] = None, server_url: Optional[str] = None
    ) -> MCPApp:
        """Get a mock MCP App by ID.

        Args:
            app_id: The UUID of the app to retrieve
            server_url: Optional server URL

        Returns:
            MCPApp: The mock MCP App with MOCK_APP_ID and MOCK_APP_NAME

        Raises:
            ValueError: If the app_id is invalid
        """
        if not (app_id or server_url):
            raise ValueError("Either app_id or server_url must be provided")

        if app_id:
            resolved_app_id = app_id
        else:
            id_hash = hash(server_url)
            raw_uuid = uuid.UUID(int=abs(id_hash) % (2**128 - 1))
            uuid_str = str(raw_uuid)
            resolved_app_id = f"app_{uuid_str}"

        return MCPApp(
            appId=resolved_app_id,
            name="Test App",
            creatorId="u_12345678-1234-1234-1234-123456789012",
            description="A mock app for testing purposes",
            createdAt=datetime.datetime(
                2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
            ),
            updatedAt=datetime.datetime(
                2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
            ),
        )

    async def create_app(self, name: str, description: Optional[str] = None) -> MCPApp:
        """Create a new mock MCP App.

        Args:
            name: The name of the MCP App
            description: Optional description for the app

        Returns:
            MCPApp: The created mock MCP App

        Raises:
            ValueError: If the name is empty or invalid
        """
        if not name or not isinstance(name, str):
            raise ValueError("App name must be a non-empty string")

        # Generate a predictable, production-format UUID based on the name
        # This ensures consistent UUIDs in the correct format for testing
        name_hash = hash(name)
        # Generate proper UUID using the hash as a seed
        raw_uuid = uuid.UUID(int=abs(name_hash) % (2**128 - 1))
        # Format to standard UUID string
        uuid_str = str(raw_uuid)

        # Add the prefix to identify this as an app entity
        prefixed_uuid = f"app_{uuid_str}"

        return MCPApp(
            appId=prefixed_uuid,
            name=name,
            creatorId="u_12345678-1234-1234-1234-123456789012",
            description=description,
            createdAt=datetime.datetime(
                2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
            ),
            updatedAt=datetime.datetime(
                2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
            ),
        )

    async def configure_app(
        self,
        app_server_url: str,
        config_params: Dict[str, Any],
    ) -> MCPAppConfiguration:
        """Create a mock MCPAppConfiguration.

        Args:
            app_server_url: The server URL of the app to configure
            config_params: Dictionary of configuration parameters (e.g. user secrets)

        Returns:
            MCPAppConfiguration: The configured MCP App

        Raises:
            ValueError: If the app_server_url or config_params is invalid
        """
        if not app_server_url or not isinstance(app_server_url, str):
            raise ValueError(f"Invalid app server URL format: {app_server_url}")

        if not config_params or not isinstance(config_params, dict):
            raise ValueError("Configuration parameters must be a non-empty dictionary")

        if app_server_url == MOCK_APP_SERVER_URL:
            config_id = MOCK_APP_CONFIG_ID
        else:
            # Generate a predictable, production-format UUID based on the app server URL
            # This ensures consistent UUIDs in the correct format for testing
            app_server_url_hash = hash(app_server_url)
            # Generate proper UUID using the hash as a seed
            raw_uuid = uuid.UUID(int=abs(app_server_url_hash) % (2**128 - 1))
            # Format to standard UUID string
            uuid_str = str(raw_uuid)

            # Add the prefix to identify this as an app entity
            config_id = f"apcnf_{uuid_str}"

        return MCPAppConfiguration(
            appConfigurationId=config_id,
            app=MCPApp(
                appId=MOCK_APP_ID,
                name=MOCK_APP_NAME if app_server_url == MOCK_APP_SERVER_URL else "App",
                creatorId="u_12345678-1234-1234-1234-123456789012",
                createdAt=datetime.datetime(
                    2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
                ),
                updatedAt=datetime.datetime(
                    2025, 6, 16, 0, 0, 0, tzinfo=datetime.timezone.utc
                ),
            ),
            creatorId="u_12345678-1234-1234-1234-123456789012",
        )

    async def list_config_params(self, app_server_url: str) -> List[str]:
        """List required configuration parameters (e.g. user secrets) for an MCP App via the API.

        Args:
            app_server_url: The server URL of the app to retrieve config params for

        Returns:
            List[str]: List of configuration parameter names

        Raises:
            ValueError: If the app_server_url is invalid
        """
        if not app_server_url or not isinstance(app_server_url, str):
            raise ValueError(f"Invalid app server URL format: {app_server_url}")

        if app_server_url == MOCK_APP_SERVER_URL:
            return ["anthropic.api_key", "openai.api_key"]
        else:
            return ["mock-params"]
