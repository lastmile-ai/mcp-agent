"""Secrets API client implementation for the MCP Agent Cloud API."""

from typing import Any, Dict, List, Optional

from mcp_agent.cli.core.api_client import APIClient
from mcp_agent.cli.core.constants import (
    SECRET_ID_PATTERN,
    SecretType,
)


class SecretsClient(APIClient):
    """Client for interacting with the Secrets API service over HTTP."""

    async def create_secret(
        self, name: str, secret_type: SecretType, value: str
    ) -> str:
        """Create a secret via the API.

        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            secret_type: DEVELOPER ("dev") or USER ("usr")
            value: The secret value (required for all secret types)

        Returns:
            str: The secret UUID/handle returned by the API

        Raises:
            ValueError: If a secret is created without a non-empty value
            httpx.HTTPError: If the API request fails
        """
        # For all secrets, non-empty values are required (based on test expectations)
        if value is None:
            raise ValueError(f"Secret '{name}' requires a non-empty value")

        # Ensure values are not empty or just whitespace
        if isinstance(value, str) and value.strip() == "":
            raise ValueError(f"Secret '{name}' requires a non-empty value")

        # Prepare request payload
        payload: Dict[str, Any] = {
            "name": name,
            "type": secret_type.value,  # Send "dev" or "usr" directly from enum value
        }

        # Add value to payload if provided
        if value is not None:
            payload["value"] = value

        # Make the API request
        response = await self.post("/secrets/create_secret", payload)

        # Parse the response to get the UUID/handle
        data = response.json()
        # Extract the secretId from the response - it should be in the secret object
        handle = data.get("secret", {}).get("secretId")

        if not handle:
            raise ValueError(
                "API did not return a valid secret handle in the expected format"
            )

        # The API should already be returning prefixed UUIDs
        # Only return the handle if it matches our expected pattern
        if not SECRET_ID_PATTERN.match(handle):
            raise ValueError(
                f"API returned an invalid secret handle format: {handle}. Expected the mcpac_sc_ prefix."
            )

        return handle

    async def get_secret_value(self, handle: str) -> str:
        """Get a secret value from the API.

        Args:
            handle: The secret UUID returned by the API

        Returns:
            str: The secret value

        Raises:
            ValueError: If the handle is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")

        response = await self.post("/secrets/get_secret_value", {"secretId": handle})

        # Parse the response to get the value
        data = response.json()
        value = data.get("value")

        if value is None:
            raise ValueError(f"Secret {handle} doesn't have a value")

        return value

    async def set_secret_value(self, handle: str, value: str) -> bool:
        """Set a secret value via the API.

        Args:
            handle: The secret UUID returned by the API
            value: The secret value to store

        Returns:
            bool: True if the operation was successful

        Raises:
            ValueError: If the handle is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")

        # Prepare request payload
        payload = {
            "secretId": handle,
            "value": value,
        }

        response = await self.post("/secrets/set_secret_value", payload)

        # Parse the response to get the success flag
        data = response.json()
        success = data.get("success", False)

        return success

    async def list_secrets(
        self, name_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List secrets via the API.

        Args:
            name_filter: Optional filter for secret names

        Returns:
            List[Dict[str, Any]]: List of secret metadata

        Raises:
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        # Prepare request payload
        payload = {}
        if name_filter:
            payload["nameFilter"] = name_filter

        response = await self.post("/secrets/list", payload)

        # Parse the response
        data = response.json()
        secrets = data.get("secrets", [])

        return secrets

    async def delete_secret(self, handle: str) -> str:
        """Delete a secret via the API.

        Args:
            handle: The secret UUID returned by the API

        Returns:
            str: The ID of the deleted secret

        Raises:
            ValueError: If the handle is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")

        # Prepare request payload
        payload = {
            "secretId": handle,
        }

        response = await self.delete("/secrets/delete_secret", payload)

        # Parse the response to get the deleted secret ID
        data = response.json()
        deleted_id = data.get("secretId")

        if not deleted_id:
            raise ValueError("API didn't return the ID of the deleted secret")

        return deleted_id

    def _is_valid_handle(self, handle: str) -> bool:
        """Check if a handle has a valid format.

        Args:
            handle: The handle to check (prefixed UUID format)

        Returns:
            bool: True if the handle has a valid format, False otherwise
        """
        if not isinstance(handle, str) or not handle:
            return False

        # Validate against the pattern (prefixed UUID format)
        return bool(SECRET_ID_PATTERN.match(handle))
