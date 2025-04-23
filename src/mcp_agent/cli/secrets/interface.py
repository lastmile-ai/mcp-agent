"""Interface definitions for secrets backend interaction."""

from abc import ABC, abstractmethod
from typing import Optional

from .constants import SecretType


class SecretsApiClientInterface(ABC):
    """Interface for interacting with the secrets backend.
    
    This interface defines the contract for CLI and runtime interaction with the
    secrets backend, whether it's the Secrets API service (standard mode) or
    directly with Vault (MVP0 mode).
    """
    
    @abstractmethod
    async def create_secret(self, name: str, type_: SecretType, value: Optional[str] = None) -> str:
        """Registers a secret and stores its value if provided.
        
        Args:
            name (str): The configuration path (e.g., 'server.bedrock.api_key').
            type_ (SecretType): DEVELOPER or USER.
            value (Optional[str]): The secret value for developer secrets.
            
        Returns:
            str: The generated handle (e.g., 'mcpac_dev_...').
            
        Raises:
            Exception: If creation fails.
        """
        pass

    @abstractmethod
    async def get_secret_value(self, handle: str) -> str:
        """Retrieves the value for a given secret handle.
        
        Args:
            handle (str): The secret handle (e.g., 'mcpac_dev_...').
            
        Returns:
            str: The secret value.
            
        Raises:
            Exception: If retrieval fails or the secret doesn't exist.
        """
        pass

    @abstractmethod
    async def set_secret_value(self, handle: str, value: str) -> None:
        """Stores/updates the value for a given secret handle.
        
        Args:
            handle (str): The secret handle (e.g., 'mcpac_dev_...' or 'mcpac_usr_...').
            value (str): The secret value to store.
            
        Raises:
            Exception: If the update fails.
        """
        pass