"""Mock Client for dry run mode.

This module provides a mock implementation of the SecretsApiClientInterface
that generates fake UUIDs instead of making real API calls.
"""

import uuid
from typing import Dict, Optional, List, Any

from ..core.constants import SecretType
from .api_client import SecretsApiClientInterface


class MockSecretsClient(SecretsApiClientInterface):
    """Mock client that generates fake UUIDs for dry run mode."""
    
    def __init__(self, api_url: str = "http://mock-api", api_key: str = "mock-key", api_token: str = None):
        """Initialize the mock client.
        
        Args:
            api_url: Mock API URL (ignored)
            api_key: Mock API key
            api_token: Unused, kept for API compatibility
        """
        self.api_url = api_url
        self.api_key = api_key
        self._created_secrets: Dict[str, Dict[str, Any]] = {}
    
    async def create_secret(self, name: str, secret_type: SecretType, value: str) -> str:
        """Create a mock secret with a fake UUID.
        
        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            secret_type: DEVELOPER ("dev") or USER ("usr") 
            value: The secret value (required for all secret types)
            
        Returns:
            str: A fake UUID for dry run mode
            
        Raises:
            ValueError: If any secret is created without a value
        """
        # Value is required for all secret types
        if value is None or value.strip() == "":
            raise ValueError(f"Secret '{name}' requires a non-empty value")
        
        # Generate a predictable fake UUID based on the name
        # This ensures consistent UUIDs for the same name
        name_hash = hash(f"{name}:{secret_type.value}")
        fake_uuid = str(uuid.UUID(int=abs(name_hash) % (2**128 - 1)))
        
        # Store the secret in the mock storage
        self._created_secrets[fake_uuid] = {
            "name": name,
            "type": secret_type.value,
            "value": value  # Value is always required now
        }
        
        return fake_uuid
    
    async def get_secret_value(self, handle: str) -> str:
        """Get a mock secret value.
        
        Args:
            handle: The secret UUID returned by create_secret
            
        Returns:
            str: The mock secret value
            
        Raises:
            ValueError: If the handle is not found
        """
        if handle not in self._created_secrets:
            raise ValueError(f"Secret {handle} not found (mock)")
        
        return self._created_secrets[handle]["value"]
    
    async def set_secret_value(self, handle: str, value: str) -> None:
        """Set a mock secret value.
        
        Args:
            handle: The secret UUID returned by create_secret
            value: The new value to set
            
        Raises:
            ValueError: If the handle is not found
        """
        if handle not in self._created_secrets:
            raise ValueError(f"Secret {handle} not found (mock)")
        
        self._created_secrets[handle]["value"] = value
    
    async def list_secrets(self, name_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List mock secrets.
        
        Args:
            name_filter: Optional filter for secret names
            
        Returns:
            List[Dict[str, Any]]: List of mock secret metadata
        """
        results = []
        
        for handle, secret in self._created_secrets.items():
            if name_filter and name_filter not in secret["name"]:
                continue
                
            results.append({
                "secretId": handle,
                "name": secret["name"],
                "type": secret["type"],
                "createdAt": "2023-01-01T00:00:00.000Z",
                "updatedAt": "2023-01-01T00:00:00.000Z"
            })
            
        return results
    
    async def delete_secret(self, handle: str) -> None:
        """Delete a mock secret.
        
        Args:
            handle: The secret UUID returned by create_secret
            
        Raises:
            ValueError: If the handle is not found
        """
        if handle not in self._created_secrets:
            raise ValueError(f"Secret {handle} not found (mock)")
            
        del self._created_secrets[handle]