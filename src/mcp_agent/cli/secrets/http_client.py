"""HTTP client implementation for the MCP Agent Cloud Secrets API."""

from typing import Optional, Dict, Any

import httpx

from .interface import SecretsApiClientInterface, SecretType


class HttpSecretsApiClient(SecretsApiClientInterface):
    """Client for interacting with the Secrets API service over HTTP."""
    
    # Use constants from constants.py
    from .constants import DEV_HANDLE_PREFIX, USR_HANDLE_PREFIX
    
    def __init__(self, api_url: str, api_token: str):
        """Initialize the HTTP client.
        
        Args:
            api_url: The URL of the Secrets API (e.g., http://localhost:3000/api/v1)
            api_token: The API authentication token
        """
        self.api_url = api_url.rstrip("/")  # Remove trailing slash for consistent URL building
        self.api_token = api_token
        
    async def create_secret(self, name: str, type_: SecretType, value: Optional[str] = None) -> str:
        """Create a secret via the Secrets API.
        
        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            type_: DEVELOPER or USER
            value: The secret value (required for DEVELOPER, optional for USER)
            
        Returns:
            str: A handle to the secret (e.g., mcpac_dev_uuid)
            
        Raises:
            ValueError: If a developer secret is created without a value
            httpx.HTTPError: If the API request fails
        """
        # For developer secrets, a value is required
        if type_ == SecretType.DEVELOPER and value is None:
            raise ValueError(f"Developer secret '{name}' requires a value")
        
        # Prepare request payload
        payload: Dict[str, Any] = {
            "name": name,
            "type": type_.value,
        }
        
        # Include value if provided
        if value is not None:
            payload["value"] = value
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/secrets",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0,  # Reasonable timeout for API operations
            )
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            # Parse the response to get the handle
            data = response.json()
            handle = data.get("id")
            
            if not handle:
                raise ValueError("API did not return a valid handle")
            
            return handle
        
    async def get_secret_value(self, handle: str) -> str:
        """Get a secret value from the Secrets API.
        
        Args:
            handle: The secret handle (e.g., mcpac_dev_uuid)
            
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
            response = await client.get(
                f"{self.api_url}/secrets/{handle}/value",
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
            handle: The secret handle (e.g., mcpac_dev_uuid)
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
            "value": value,
        }
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.api_url}/secrets/{handle}/value",
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
        """Check if a handle has a valid format.
        
        Args:
            handle: The handle to check
            
        Returns:
            bool: True if the handle has a valid format, False otherwise
        """
        return (handle.startswith(self.DEV_HANDLE_PREFIX) or 
                handle.startswith(self.USR_HANDLE_PREFIX))