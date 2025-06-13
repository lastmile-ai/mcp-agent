"""Mock Client for dry run mode.

This module provides a mock implementation of the MCPAppClient interface
that generates fake app data instead of making real API calls.
"""

import uuid
from typing import Dict, Optional, List, Any

from .api_client import MCPApp
from ..core.constants import SecretType, UUID_PREFIX


MOCK_APP_NAME = "Test App"
MOCK_APP_ID = "app_aece3598-d229-46d8-83fb-8c61ca7cd435"


class MockMCPAppClient:
    """Mock client that generates fake app data for dry run mode."""

    def __init__(
        self, api_url: str = "http://mock-api", api_key: str = "mock-key"
    ):
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

    async def create_app(
        self, name: str, description: Optional[str] = None
    ) -> MCPApp:
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
            createdAt="2025-06-16T00:00:00Z",
            updatedAt="2025-06-16T00:00:00Z",
        )
