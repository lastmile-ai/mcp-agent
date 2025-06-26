"""Utilities for resolving secrets from configuration to environment variables."""

import re
from typing import Dict, Any, Optional
from .api_client import SecretsClient


class SecretsResolver:
    """Resolves secret handles in configuration to actual values."""
    
    def __init__(self, client: SecretsClient):
        """Initialize the resolver with a secrets client.
        
        Args:
            client: SecretsClient instance for API communication
        """
        self.client = client
        self.handle_pattern = re.compile(r'^mcpac_sc_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        
    def _is_secret_handle(self, value: Any) -> bool:
        """Check if a value is a secret handle."""
        return isinstance(value, str) and bool(self.handle_pattern.match(value))
    
    async def resolve_in_place(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve all secret handles in config, replacing them with actual values.
        
        This modifies the configuration structure in-place, replacing secret handles
        with their resolved values while maintaining the original structure.
        
        Args:
            config: Configuration dictionary potentially containing secret handles
            
        Returns:
            The same config structure with secret handles replaced by values
            
        Raises:
            ValueError: If API credentials are missing
            UnauthenticatedError: If API authentication fails
            Exception: If any secret resolution fails
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Check for API credentials before making any requests
        if not hasattr(self.client, 'api_key') or not self.client.api_key:
            error_msg = (
                "Missing API credentials. The deployment daemon requires:\n"
                "  export MCP_API_BASE_URL=http://localhost:3000/api\n"
                "  export MCP_API_KEY=<service-account-api-key>"
            )
            logger.error(error_msg)
            raise ValueError("Missing MCP_API_KEY environment variable")
        
        async def process_value(value: Any, path: str = "") -> Any:
            """Process a single value, resolving if it's a secret handle."""
            if self._is_secret_handle(value):
                try:
                    logger.debug(f"Resolving secret handle at {path}: {value}")
                    resolved = await self.client.get_secret_value(value)
                    logger.info(f"Successfully resolved secret at {path}")
                    return resolved
                except UnauthenticatedError as e:
                    logger.error(
                        f"Authentication failed for secret at {path}: {e}\n"
                        f"Please ensure:\n"
                        f"  1. MCP_API_KEY environment variable is set\n"
                        f"  2. The API key is valid and not expired\n"
                        f"  3. The API key has permission to read secret {value}"
                    )
                    # Fail fast - authentication errors are not recoverable
                    raise
                except Exception as e:
                    logger.error(
                        f"Failed to resolve secret at {path}: {type(e).__name__}: {e}\n"
                        f"Secret handle: {value}"
                    )
                    # Fail fast - if the app needs this secret, it won't work without it
                    raise RuntimeError(f"Failed to resolve secret at {path}: {e}") from e
            elif isinstance(value, dict):
                # Recursively process dictionaries
                result = {}
                for k, v in value.items():
                    new_path = f"{path}.{k}" if path else k
                    result[k] = await process_value(v, new_path)
                return result
            elif isinstance(value, list):
                # Process lists
                result = []
                for i, item in enumerate(value):
                    new_path = f"{path}[{i}]"
                    result.append(await process_value(item, new_path))
                return result
            else:
                # Return other types as-is
                return value
        
        # Import the exception type we need
        from ..core.api_client import UnauthenticatedError
        
        logger.info("Starting secrets resolution...")
        try:
            result = await process_value(config)
            logger.info("Successfully resolved all secrets")
            return result
        except Exception:
            logger.error("Secrets resolution failed - deployment cannot proceed")
            raise