"""Mock implementation of the SecretsClient for testing."""

import uuid
from typing import Any, Dict, List, Optional

from mcp_agent.cli.core.constants import SecretType


class MockSecretsClient:
    """Mock client for testing secret operations without a real API."""

    def __init__(
        self, api_url: str = "http://mock.test/api", api_key: str = "mock-api-key"
    ):
        """Initialize the mock client.

        Args:
            api_url: Mock API URL (unused except for initialization)
            api_key: Mock API key (unused except for initialization)
        """
        self.api_url = api_url
        self.api_key = api_key
        # Storage for mock secrets
        self._secrets: Dict[str, Dict[str, Any]] = {}

    async def create_secret(
        self, name: str, secret_type: SecretType, value: Optional[str] = None
    ) -> str:
        """Create a mock secret.

        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            secret_type: DEVELOPER ("dev") or USER ("usr")
            value: The secret value (required for all secret types)

        Returns:
            str: The generated secret UUID/handle

        Raises:
            ValueError: If a secret is created without a non-empty value
        """
        # For all secrets, non-empty values are required
        if value is None:
            raise ValueError(f"Secret '{name}' requires a non-empty value")

        # Ensure values are not empty or just whitespace
        if isinstance(value, str) and value.strip() == "":
            raise ValueError(f"Secret '{name}' requires a non-empty value")

        # Generate a mock handle
        handle = str(uuid.uuid4())

        # Store the secret
        self._secrets[handle] = {
            "id": handle,
            "name": name,
            "type": secret_type.value,
            "value": value,
            "createdAt": "2025-04-29T12:00:00Z",
            "updatedAt": "2025-04-29T12:00:00Z",
        }

        return handle

    async def get_secret_value(self, handle: str) -> str:
        """Get a secret value.

        Args:
            handle: The secret UUID

        Returns:
            str: The secret value

        Raises:
            ValueError: If handle doesn't exist or has no value
        """
        if handle not in self._secrets:
            raise ValueError(f"Secret {handle} not found")

        value = self._secrets[handle].get("value")
        if value is None:
            raise ValueError(f"Secret {handle} doesn't have a value")

        return value

    async def set_secret_value(self, handle: str, value: str) -> bool:
        """Set a secret value.

        Args:
            handle: The secret UUID
            value: The new secret value

        Returns:
            bool: True if successful

        Raises:
            ValueError: If handle doesn't exist
        """
        if handle not in self._secrets:
            raise ValueError(f"Secret {handle} not found")

        # Update the value
        self._secrets[handle]["value"] = value
        self._secrets[handle]["updatedAt"] = "2025-04-29T13:00:00Z"

        return True

    async def list_secrets(
        self, name_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List secrets.

        Args:
            name_filter: Optional filter for secret names

        Returns:
            List[Dict[str, Any]]: List of secret metadata
        """
        # Convert stored secrets to list
        secrets = list(self._secrets.values())

        # Apply name filter if provided
        if name_filter:
            secrets = [s for s in secrets if name_filter in s["name"]]

        return secrets

    async def delete_secret(self, handle: str) -> str:
        """Delete a secret.

        Args:
            handle: The secret UUID

        Returns:
            str: The ID of the deleted secret

        Raises:
            ValueError: If handle doesn't exist
        """
        if handle not in self._secrets:
            raise ValueError(f"Secret {handle} not found")

        # Remove the secret
        del self._secrets[handle]

        return handle
