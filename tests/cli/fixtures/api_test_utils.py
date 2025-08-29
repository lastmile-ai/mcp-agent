"""Utilities for API integration tests."""

import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Tuple

# Import the JWT generator from our utils package
from ..utils.jwt_generator import generate_jwt


class APIMode(Enum):
    """API test mode."""

    LOCAL = "local"  # Use a local development web app instance
    REMOTE = "remote"  # Use a remote web app instance
    AUTO = "auto"  # Auto-detect based on environment


class APITestManager:
    """Manages API testing configurations."""

    # Environment variable names
    API_URL_ENV = "MCP_API_BASE_URL"
    API_KEY_ENV = "MCP_API_KEY"

    # Default values
    DEFAULT_LOCAL_API_URL = "http://localhost:3000/api"

    def __init__(self, mode: APIMode = APIMode.AUTO, force_check: bool = False):
        """Initialize the API test manager.

        Args:
            mode: The API mode to use.
            force_check: Force checking the API connection even if it was already set up.
        """
        self.mode = mode
        self.force_check = force_check
        self.base_dir = Path(
            __file__
        ).parent.parent.parent.parent.parent  # mcp-agent-cloud directory

    def setup(self) -> Tuple[str, str]:
        """Set up the API for testing.

        Returns:
            Tuple of (api_url, api_key)
        """
        # Check if API credentials are already set and we're not forcing a check
        api_url = os.environ.get(self.API_URL_ENV)
        api_key = os.environ.get(self.API_KEY_ENV)

        if not self.force_check and api_url and api_key:
            # Verify the API connection
            if self._verify_api_connection(api_url, api_key):
                print(f"Using existing API credentials for {api_url}")
                return api_url, api_key

        # Determine the mode to use
        if self.mode == APIMode.AUTO:
            # Check if remote credentials are available
            api_url = os.environ.get(self.API_URL_ENV)
            api_key = os.environ.get(self.API_KEY_ENV)

            if api_url and api_key:
                # Try to use remote
                if self._verify_api_connection(api_url, api_key):
                    print(f"Successfully connected to remote API at {api_url}")
                    return api_url, api_key
                else:
                    print(
                        f"Failed to connect to remote API at {api_url}, falling back to local"
                    )

            # Fall back to local
            self.mode = APIMode.LOCAL

        if self.mode == APIMode.REMOTE:
            # Require remote credentials to be set
            api_url = os.environ.get(self.API_URL_ENV)
            api_key = os.environ.get(self.API_KEY_ENV)

            if not api_url or not api_key:
                raise RuntimeError(
                    f"Remote API mode requires {self.API_URL_ENV} and {self.API_KEY_ENV} environment variables"
                )

            if not self._verify_api_connection(api_url, api_key):
                raise RuntimeError(f"Failed to connect to remote API at {api_url}")

            print(f"Successfully connected to remote API at {api_url}")
            return api_url, api_key

        # Local mode
        api_url = self.DEFAULT_LOCAL_API_URL
        api_key = os.environ.get(self.API_KEY_ENV)

        # If no token is provided, generate one for testing
        if not api_key:
            print("No API key found in environment, generating a test JWT token...")
            # Get the NEXTAUTH_SECRET from the environment or .env file
            nextauth_secret = os.environ.get("NEXTAUTH_SECRET")

            # If not in environment, try to read from www/.env file
            if not nextauth_secret:
                env_path = str(self.base_dir / "www" / ".env")
                if os.path.exists(env_path):
                    print(f"Reading NEXTAUTH_SECRET from {env_path}")
                    with open(env_path, "r") as f:
                        for line in f:
                            if line.startswith("NEXTAUTH_SECRET="):
                                # Extract value between quotes if present
                                parts = line.strip().split("=", 1)
                                if len(parts) == 2:
                                    secret = parts[1].strip()
                                    # Remove surrounding quotes if present
                                    if (
                                        secret.startswith('"') and secret.endswith('"')
                                    ) or (
                                        secret.startswith("'") and secret.endswith("'")
                                    ):
                                        secret = secret[1:-1]
                                    nextauth_secret = secret
                                    # Save in environment
                                    os.environ["NEXTAUTH_SECRET"] = nextauth_secret
                                    print("Found NEXTAUTH_SECRET in .env file")
                                    break

            # If still not found, use the hardcoded value from the .env file
            if not nextauth_secret:
                print(
                    "Warning: NEXTAUTH_SECRET not found in environment or .env. Using hardcoded secret for testing."
                )
                nextauth_secret = "3Jk0h98K1KKB7Jyh3/Kgp0bAKM0DSMcx1Jk7FJ6boNw"
                # Set it in the environment for future use
                os.environ["NEXTAUTH_SECRET"] = nextauth_secret

            # Generate a test token with required fields
            api_key = generate_jwt(
                user_id=f"test-user-{uuid.uuid4()}",
                email="test@example.com",
                name="Test User",
                api_token=True,
                prefix=True,  # Add the prefix for API tokens
                nextauth_secret=nextauth_secret,
            )
            print(f"Generated test API key: {api_key[:15]}...{api_key[-5:]}")
            # Store it in the environment
            os.environ[self.API_KEY_ENV] = api_key

        # Verify connection to local API
        if not self._verify_api_connection(api_url, api_key):
            import httpx

            # Try to get more diagnostic information
            try:
                # Check if web app is running but has errors
                response = httpx.get(
                    f"{api_url.rstrip('/api')}/api/health", timeout=2.0
                )

                # Check for API token errors by testing a secrets endpoint
                try:
                    secrets_response = httpx.post(
                        f"{api_url}/secrets/create_secret",
                        json={"name": "test", "type": "dev", "value": "test"},
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=2.0,
                    )
                    if "Error decoding API token" in secrets_response.text:
                        raise RuntimeError(
                            f"API token validation error. "
                            f"The provided API key '{api_key}' is not valid for the running web app. "
                            f"Use an appropriate test token for this environment."
                        )
                except Exception:
                    # Ignore connection errors here
                    pass

                if response.status_code == 500:
                    if "Can't resolve '@mcpac/proto" in response.text:
                        raise RuntimeError(
                            "API is running but returning 500 errors. "
                            "Missing proto files. Please generate the proto files first."
                        )
                    else:
                        raise RuntimeError(
                            "API is running but returning 500 errors. "
                            "Check the web app logs for details."
                        )
            except httpx.ConnectError:
                # If we can't connect at all, it's likely that the web app isn't running
                pass

            # Default error message
            raise RuntimeError(
                f"Failed to connect to local API at {api_url}. "
                f"Please ensure the web app is running with 'cd www && pnpm run webdev'."
            )

        print(f"Successfully connected to local API at {api_url}")
        os.environ[self.API_URL_ENV] = api_url
        os.environ[self.API_KEY_ENV] = api_key

        return api_url, api_key

    def _verify_api_connection(self, api_url: str, api_key: str) -> bool:
        """Verify that we can connect to the API.

        Args:
            api_url: The API URL.
            api_key: The API key.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            import httpx

            # Make a test request to the health endpoint
            # Use the direct /api/health endpoint instead of stripping the last part
            if api_url.endswith("/api"):
                health_url = api_url + "/health"
            else:
                health_url = api_url.rstrip("/") + "/health"

            print(f"Checking API health at: {health_url}")
            response = httpx.get(health_url, timeout=5.0)

            # Check if the connection is successful
            return response.status_code == 200
        except Exception as e:
            print(f"Error connecting to API: {e}")
            return False


def get_api_manager(
    mode: APIMode = APIMode.AUTO, force_check: bool = False
) -> APITestManager:
    """Get an APITestManager instance.

    Args:
        mode: The API mode to use.
        force_check: Force checking the API connection even if it was already set up.

    Returns:
        APITestManager instance.
    """
    return APITestManager(mode=mode, force_check=force_check)


def setup_api_for_testing(
    mode: APIMode = APIMode.AUTO, force_check: bool = False
) -> Tuple[str, str]:
    """Set up the API for testing.

    Args:
        mode: The API mode to use.
        force_check: Force checking the API connection even if it was already set up.

    Returns:
        Tuple of (api_url, api_key)
    """
    manager = get_api_manager(mode=mode, force_check=force_check)
    return manager.setup()


if __name__ == "__main__":
    # When run directly, verify API connection and print results
    try:
        api_url, api_key = setup_api_for_testing()
        print(f"API URL: {api_url}")
        print(f"API Key: {'*' * 6 + api_key[-4:] if api_key else 'Not set'}")
        print("API connection successful!")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
