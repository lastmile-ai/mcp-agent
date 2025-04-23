"""Direct Vault client implementation for the MCP Agent Cloud SDK."""

import asyncio
import uuid
from typing import Optional

import hvac

from .interface import SecretsApiClientInterface, SecretType


class DirectVaultSecretsApiClient(SecretsApiClientInterface):
    """A client that directly interacts with HashiCorp Vault.
    
    This implementation is for MVP0 and development purposes, allowing the CLI
    to work without the Secrets API service. It should not be used in production.
    """
    
    # Use constants from constants.py
    from .constants import VAULT_SECRETS_PATH, MVP0_DEV_HANDLE_PREFIX as DEV_HANDLE_PREFIX, MVP0_USR_HANDLE_PREFIX as USR_HANDLE_PREFIX
    
    def __init__(self, vault_addr: str, vault_token: str):
        """Initialize the direct Vault client.
        
        Args:
            vault_addr: The Vault server address (e.g., http://127.0.0.1:8200)
            vault_token: The Vault token with appropriate permissions
        """
        self.vault_client = hvac.Client(url=vault_addr, token=vault_token)
    
    async def create_secret(self, name: str, type_: SecretType, value: Optional[str] = None) -> str:
        """Create a secret in Vault and return a handle.
        
        Args:
            name: The configuration path (e.g., 'server.bedrock.api_key')
            type_: DEVELOPER or USER
            value: The secret value (required for DEVELOPER, optional for USER)
            
        Returns:
            str: A handle to the secret (e.g., mcpac_mvp0_dev_uuid)
            
        Raises:
            ValueError: If a developer secret is created without a value
            hvac.exceptions.VaultError: If Vault operations fail
        """
        # Generate a unique handle based on secret type
        handle = self._generate_handle(type_)
        
        # For developer secrets, a value is required
        if type_ == SecretType.DEVELOPER and value is None:
            raise ValueError(f"Developer secret '{name}' requires a value")
        
        # Create secret metadata
        secret_data = {
            "name": name,
            "type": type_.value,
        }
        
        # If value is provided, add it to the secret data
        if value is not None:
            secret_data["value"] = value
        
        # Run the Vault operation in a thread to avoid blocking
        def _create_secret():
            # Store secrets under the path allowed by the policy
            self.vault_client.secrets.kv.v2.create_or_update_secret(
                path=f"{self.VAULT_SECRETS_PATH}/{handle}",
                mount_point="secret",
                secret=secret_data,
            )
        
        # Run the blocking operation in a thread pool
        await asyncio.to_thread(_create_secret)
        
        return handle
    
    async def get_secret_value(self, handle: str) -> str:
        """Get a secret value from Vault.
        
        Args:
            handle: The secret handle (e.g., mcpac_mvp0_dev_uuid)
            
        Returns:
            str: The secret value
            
        Raises:
            ValueError: If the handle is invalid or the secret doesn't have a value
            hvac.exceptions.VaultError: If Vault operations fail
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")
        
        # Run the Vault operation in a thread to avoid blocking
        def _get_secret():
            response = self.vault_client.secrets.kv.v2.read_secret_version(
                path=f"{self.VAULT_SECRETS_PATH}/{handle}",
                mount_point="secret",
                raise_on_deleted_version=True
            )
            
            # Extract the secret data
            secret_data = response["data"]["data"]
            
            # Check if the value exists
            if "value" not in secret_data:
                raise ValueError(f"Secret {handle} doesn't have a value")
            
            return secret_data["value"]
        
        # Run the blocking operation in a thread pool
        return await asyncio.to_thread(_get_secret)
    
    async def set_secret_value(self, handle: str, value: str) -> None:
        """Set a secret value in Vault.
        
        Args:
            handle: The secret handle (e.g., mcpac_mvp0_dev_uuid)
            value: The secret value to store
            
        Raises:
            ValueError: If the handle is invalid
            hvac.exceptions.VaultError: If Vault operations fail
        """
        if not self._is_valid_handle(handle):
            raise ValueError(f"Invalid handle format: {handle}")
        
        # Run the Vault operation in a thread to avoid blocking
        def _set_secret():
            # First read the current secret to preserve metadata
            try:
                response = self.vault_client.secrets.kv.v2.read_secret_version(
                    path=f"{self.VAULT_SECRETS_PATH}/{handle}",
                    mount_point="secret",
                    raise_on_deleted_version=True
                )
                secret_data = response["data"]["data"]
            except Exception:
                # Secret doesn't exist yet, initialize with empty data
                secret_data = {}
            
            # Update the value
            secret_data["value"] = value
            
            # Write the updated secret
            self.vault_client.secrets.kv.v2.create_or_update_secret(
                path=f"{self.VAULT_SECRETS_PATH}/{handle}",
                mount_point="secret",
                secret=secret_data,
            )
        
        # Run the blocking operation in a thread pool
        await asyncio.to_thread(_set_secret)
    
    def _generate_handle(self, type_: SecretType) -> str:
        """Generate a unique handle for a secret.
        
        Args:
            type_: The secret type (DEVELOPER or USER)
            
        Returns:
            str: A unique handle with the appropriate prefix
        """
        unique_id = str(uuid.uuid4())
        
        # Strict check to ensure type_ is a SecretType enum
        if not isinstance(type_, SecretType):
            raise TypeError(f"Expected SecretType enum, got {type(type_).__name__}: {type_}")
            
        if type_ == SecretType.DEVELOPER:
            return f"{self.DEV_HANDLE_PREFIX}{unique_id}"
        else:
            return f"{self.USR_HANDLE_PREFIX}{unique_id}"
    
    def _is_valid_handle(self, handle: str) -> bool:
        """Check if a handle has a valid format.
        
        Args:
            handle: The handle to check
            
        Returns:
            bool: True if the handle has a valid format, False otherwise
        """
        return (handle.startswith(self.DEV_HANDLE_PREFIX) or 
                handle.startswith(self.USR_HANDLE_PREFIX))