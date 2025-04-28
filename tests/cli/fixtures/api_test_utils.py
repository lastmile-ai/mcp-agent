"""Utilities for API integration tests."""

import os
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple


class APIMode(Enum):
    """API test mode."""
    LOCAL = "local"  # Use a local development web app instance
    REMOTE = "remote"  # Use a remote web app instance
    AUTO = "auto"  # Auto-detect based on environment


class APITestManager:
    """Manages API testing configurations."""
    
    # Environment variable names
    API_URL_ENV = "MCP_SECRETS_API_URL"
    API_TOKEN_ENV = "MCP_API_TOKEN"
    
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
        self.base_dir = Path(__file__).parent.parent.parent.parent.parent  # mcp-agent-cloud directory
    
    def setup(self) -> Tuple[str, str]:
        """Set up the API for testing.
        
        Returns:
            Tuple of (api_url, api_token)
        """
        # Check if API credentials are already set and we're not forcing a check
        api_url = os.environ.get(self.API_URL_ENV)
        api_token = os.environ.get(self.API_TOKEN_ENV)
        
        if not self.force_check and api_url and api_token:
            # Verify the API connection
            if self._verify_api_connection(api_url, api_token):
                print(f"Using existing API credentials for {api_url}")
                return api_url, api_token
        
        # Determine the mode to use
        if self.mode == APIMode.AUTO:
            # Check if remote credentials are available
            api_url = os.environ.get(self.API_URL_ENV)
            api_token = os.environ.get(self.API_TOKEN_ENV)
            
            if api_url and api_token:
                # Try to use remote
                if self._verify_api_connection(api_url, api_token):
                    print(f"Successfully connected to remote API at {api_url}")
                    return api_url, api_token
                else:
                    print(f"Failed to connect to remote API at {api_url}, falling back to local")
            
            # Fall back to local
            self.mode = APIMode.LOCAL
        
        if self.mode == APIMode.REMOTE:
            # Require remote credentials to be set
            api_url = os.environ.get(self.API_URL_ENV)
            api_token = os.environ.get(self.API_TOKEN_ENV)
            
            if not api_url or not api_token:
                raise RuntimeError(f"Remote API mode requires {self.API_URL_ENV} and {self.API_TOKEN_ENV} environment variables")
            
            if not self._verify_api_connection(api_url, api_token):
                raise RuntimeError(f"Failed to connect to remote API at {api_url}")
            
            print(f"Successfully connected to remote API at {api_url}")
            return api_url, api_token
        
        # Local mode
        api_url = self.DEFAULT_LOCAL_API_URL
        api_token = os.environ.get(self.API_TOKEN_ENV)
        
        if not api_token:
            raise RuntimeError(f"Local API mode requires {self.API_TOKEN_ENV} environment variable")
        
        # Verify connection to local API
        if not self._verify_api_connection(api_url, api_token):
            import httpx
            
            # Try to get more diagnostic information
            try:
                # Check if web app is running but has errors
                response = httpx.get(f"{api_url.rstrip('/api')}/api/health", timeout=2.0)
                
                # Check for API token errors by testing a secrets endpoint
                try:
                    secrets_response = httpx.post(
                        f"{api_url}/secrets/create_secret",
                        json={"name": "test", "type": "dev", "value": "test"},
                        headers={"Authorization": f"Bearer {api_token}"},
                        timeout=2.0
                    )
                    if "Error decoding API token" in secrets_response.text:
                        raise RuntimeError(
                            f"API token validation error. "
                            f"The provided token '{api_token}' is not valid for the running web app. "
                            f"Use an appropriate test token for this environment."
                        )
                except:
                    # Ignore connection errors here
                    pass
                
                if response.status_code == 500:
                    if "Can't resolve '@mcpac/proto" in response.text:
                        raise RuntimeError(
                            f"API is running but returning 500 errors. "
                            f"Missing proto files. Please generate the proto files first."
                        )
                    else:
                        raise RuntimeError(
                            f"API is running but returning 500 errors. "
                            f"Check the web app logs for details."
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
        os.environ[self.API_TOKEN_ENV] = api_token
        
        return api_url, api_token
    
    def _verify_api_connection(self, api_url: str, api_token: str) -> bool:
        """Verify that we can connect to the API.
        
        Args:
            api_url: The API URL.
            api_token: The API token.
            
        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            import httpx
            
            # Make a test request to the health endpoint
            # Use the direct /api/health endpoint instead of stripping the last part
            if api_url.endswith('/api'):
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


def get_api_manager(mode: APIMode = APIMode.AUTO, force_check: bool = False) -> APITestManager:
    """Get an APITestManager instance.
    
    Args:
        mode: The API mode to use.
        force_check: Force checking the API connection even if it was already set up.
        
    Returns:
        APITestManager instance.
    """
    return APITestManager(mode=mode, force_check=force_check)


def setup_api_for_testing(mode: APIMode = APIMode.AUTO, force_check: bool = False) -> Tuple[str, str]:
    """Set up the API for testing.
    
    Args:
        mode: The API mode to use.
        force_check: Force checking the API connection even if it was already set up.
        
    Returns:
        Tuple of (api_url, api_token)
    """
    manager = get_api_manager(mode=mode, force_check=force_check)
    return manager.setup()


if __name__ == "__main__":
    # When run directly, verify API connection and print results
    try:
        api_url, api_token = setup_api_for_testing()
        print(f"API URL: {api_url}")
        print(f"API Token: {'*' * 6 + api_token[-4:] if api_token else 'Not set'}")
        print("API connection successful!")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)