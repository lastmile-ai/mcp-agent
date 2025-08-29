"""Utilities for resolving secrets from configuration to environment variables."""

from typing import Any, Dict

from pydantic import BaseModel

from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import SECRET_ID_PATTERN

from .api_client import SecretsClient
from .yaml_tags import DeveloperSecret, UserSecret, load_yaml_with_secrets


class SafeSecretsConfig(BaseModel):
    """Configuration for secrets resolution via yaml.
    Safely loads secrets from a yaml file into a dict (safe_config),
    excluding those values with unresolved secret yaml tags
    (!developer_secret, !user_secret), which are stored in
    separate sets with dot-notation paths.
    """

    config: Dict[str, Any] = {}
    developer_secret_tag_keys: set[str] = set()
    user_secret_tag_keys: set[str] = set()


class SecretsResolver:
    """Resolves secret handles in configuration to actual values."""

    def __init__(self, client: SecretsClient):
        """Initialize the resolver with a secrets client.

        Args:
            client: SecretsClient instance for API communication
        """
        self.client = client
        self.handle_pattern = SECRET_ID_PATTERN

    def _is_secret_handle(self, value: Any) -> bool:
        """Check if a value is a secret handle."""
        return isinstance(value, str) and bool(self.handle_pattern.match(value))

    def load_config(self, config_path: str) -> SafeSecretsConfig:
        """Safely load a secrets configuration from a file, accounting for yaml tags.

        Args:
            config_path: Path to the configuration file

        Returns:
            SafeSecretsConfig: An instance containing the safe config and sets of secret tags
        """
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
            source_config = load_yaml_with_secrets(content)

        developer_secrets = set()
        user_secrets = set()

        def strip_secrets(node: Any, path: str = "") -> Any:
            if isinstance(node, dict):
                result = {}
                for k, v in node.items():
                    sub_path = f"{path}.{k}" if path else k
                    stripped = strip_secrets(v, sub_path)
                    if stripped is not None:
                        result[k] = stripped
                return result if result else None

            elif isinstance(node, DeveloperSecret):
                developer_secrets.add(path)
                return None

            elif isinstance(node, UserSecret):
                user_secrets.add(path)
                return None

            else:
                return node

        stripped_config = strip_secrets(source_config) or {}

        return SafeSecretsConfig(
            config=stripped_config,
            developer_secret_tag_keys=developer_secrets,
            user_secret_tag_keys=user_secrets,
        )

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
        if not hasattr(self.client, "api_key") or not self.client.api_key:
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
                    raise RuntimeError(
                        f"Failed to resolve secret at {path}: {e}"
                    ) from e
            elif isinstance(value, dict):
                # Recursively process dictionaries
                result = {}
                for k, v in value.items():
                    new_path = f"{path}.{k}" if path else k
                    result[k] = await process_value(v, new_path)
                return result
            elif isinstance(value, list):
                # Process lists
                result_list = []
                for i, item in enumerate(value):
                    new_path = f"{path}[{i}]"
                    result_list.append(await process_value(item, new_path))
                return result_list
            else:
                # Return other types as-is
                return value

        logger.info("Starting secrets resolution...")
        try:
            result = await process_value(config)
            logger.info("Successfully resolved all secrets")
            return result
        except Exception:
            logger.error("Secrets resolution failed - deployment cannot proceed")
            raise
