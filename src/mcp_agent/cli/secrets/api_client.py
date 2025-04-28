"""API client implementation for the MCP Agent Cloud Secrets API."""

from typing import Optional, Dict, Any, List

import httpx

from .constants import SecretType  # Removed SECRET_TYPE_PATHS, using SecretType.value directly


class SecretsClient:
    """Client for interacting with the Secrets API service over HTTP."""
    
    def __init__(self, api_url: str, api_token: str):
        """Initialize the API client.
        
        Args:
            api_url: The URL of the Secrets API (e.g., http://localhost:3000/api)
            api_token: The API authentication token
        """
        self.api_url = api_url.rstrip("/")  # Remove trailing slash for consistent URL building
        self.api_token = api_token
        
    async def create_secret(self, name: str, secret_type: SecretType, value: Optional[str] = None) -> str:
        """Create a secret via the Secrets API.
        
        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            secret_type: DEVELOPER ("dev") or USER ("usr") 
            value: The secret value (required for DEVELOPER, optional for USER)
            
        Returns:
            str: The secret UUID/handle returned by the API
            
        Raises:
            ValueError: If a developer secret is created without a value
            httpx.HTTPError: If the API request fails
        """
        # For developer secrets, a value is required
        if secret_type == SecretType.DEVELOPER and value is None:
            raise ValueError(f"Developer secret '{name}' requires a value")
        
        # Prepare request payload
        payload: Dict[str, Any] = {
            "name": name,
            "type": secret_type.value,  # Send "dev" or "usr" directly from enum value
        }
        
        # Include value if provided (required for API)
        # For user secrets, we'll send an empty string as the API requires a value
        payload["value"] = value if value is not None else ""
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/secrets/create_secret",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0,  # Reasonable timeout for API operations
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            # Parse the response to get the UUID/handle
            data = response.json()
            # Extract the secretId (UUID) from the response - it should be in the secret object
            handle = data.get("secret", {}).get("secretId")
            
            if not handle:
                raise ValueError("API did not return a valid secret handle in the expected format")
            
            # Validate that the returned value is a proper UUID format
            if not self._is_valid_handle(handle):
                raise ValueError(f"API returned an invalid UUID/handle format: {handle}")
            
            return handle
        
    async def get_secret_value(self, handle: str) -> str:
        """Get a secret value from the Secrets API.
        
        Args:
            handle: The secret ID returned by the API (Prisma UUID)
            
        Returns:
            str: The secret value
            
        Raises:
            ValueError: If the handle is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/secrets/get_secret_value",
                json={"secretId": handle},
                headers=self._get_headers(),
                timeout=30.0,
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            # Parse the response to get the value
            data = response.json()
            value = data.get("value")
            
            if value is None:
                raise ValueError(f"Secret {handle} doesn't have a value")
            
            return value
        
    async def set_secret_value(self, handle: str, value: str) -> None:
        """Set a secret value via the Secrets API.
        
        Args:
            handle: The secret ID returned by the API (Prisma UUID)
            value: The secret value to store
            
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
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.api_url}/secrets/set_secret_value",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0,
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
            
    async def list_secrets(self, name_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List secrets via the Secrets API.
        
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
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/secrets/list",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0,
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            # Parse the response
            data = response.json()
            secrets = data.get("secrets", [])
            
            return secrets
            
    async def delete_secret(self, handle: str) -> None:
        """Delete a secret via the Secrets API.
        
        Args:
            handle: The secret ID returned by the API (Prisma UUID)
            
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
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/secrets/delete_secret",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0,
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get the headers for API requests.
        
        Returns:
            Dict[str, str]: The request headers
        """
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    def _is_valid_handle(self, handle: str) -> bool:
        """Check if a handle has a valid UUID format.
        
        Args:
            handle: The UUID handle to check
            
        Returns:
            bool: True if the handle has a valid UUID format, False otherwise
        """
        from .constants import HANDLE_PATTERN
        
        if not isinstance(handle, str) or not handle:
            return False
            
        # Validate against the UUID pattern
        return bool(HANDLE_PATTERN.match(handle))