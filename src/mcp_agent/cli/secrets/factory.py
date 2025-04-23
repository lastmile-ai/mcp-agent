"""Factory functions for creating secrets clients."""

from typing import Optional

from .interface import SecretsApiClientInterface
from .direct_vault_client import DirectVaultSecretsApiClient
from .constants import SecretsMode
from ..config import settings


# Import the HTTP client only if available
try:
    from .http_client import HttpSecretsApiClient
    _http_client_available = True
except ImportError:
    _http_client_available = False


def get_secrets_client(
    mode: SecretsMode,
    vault_addr: Optional[str] = None,
    vault_token: Optional[str] = None,
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
) -> SecretsApiClientInterface:
    """Create a secrets client instance based on the specified mode.
    
    Args:
        mode: The secrets mode to use (direct_vault or api)
        vault_addr: The Vault server address (required for direct_vault mode)
        vault_token: The Vault token (required for direct_vault mode)
        api_url: The Secrets API URL (required for api mode)
        api_token: The Secrets API token (required for api mode)
        
    Returns:
        A SecretsApiClientInterface implementation
        
    Raises:
        ValueError: If required parameters are missing for the selected mode
    """
    # Use environment variables as defaults if not provided
    vault_addr = vault_addr or settings.VAULT_ADDR
    vault_token = vault_token or settings.VAULT_TOKEN
    api_url = api_url or settings.SECRETS_API_URL
    api_token = api_token or settings.SECRETS_API_TOKEN
    
    if mode == SecretsMode.DIRECT_VAULT:
        if not vault_addr:
            raise ValueError("vault_addr is required for direct_vault mode")
        if not vault_token:
            raise ValueError("vault_token is required for direct_vault mode")
            
        return DirectVaultSecretsApiClient(
            vault_addr=vault_addr,
            vault_token=vault_token
        )
    elif mode == SecretsMode.API:
        if not _http_client_available:
            raise ImportError("HTTP client is not available. Please install the required dependencies.")
            
        if not api_url:
            raise ValueError("api_url is required for api mode")
        if not api_token:
            raise ValueError("api_token is required for api mode")
            
        return HttpSecretsApiClient(
            api_url=api_url,
            api_token=api_token
        )
    else:
        raise ValueError(f"Unknown secrets mode: {mode}")