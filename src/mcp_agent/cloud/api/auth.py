"""
Authentication for MCP Agent Cloud API.

This module provides authentication middleware for protecting the API endpoints
with a master API key.
"""

import logging
import os
from typing import Optional, Callable, Awaitable

from aiohttp import web
from aiohttp.web import Request, Response, middleware

# Configure logger
logger = logging.getLogger("mcp_cloud.auth")


class MasterApiKeyAuthenticator:
    """
    Authenticator for the MCP Agent Cloud API using a master API key.
    
    Verifies that API requests include the correct master API key in the
    X-Master-API-Key header.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the authenticator with an API key.
        
        Args:
            api_key: The master API key. If None, will read from MCP_CLOUD_API_KEY
                    environment variable.
        """
        # If API key is not provided, try to read from environment
        if api_key is None:
            api_key = os.environ.get("MCP_CLOUD_API_KEY")
        
        self.api_key = api_key
        
        # Log warning if no API key is configured
        if not self.api_key:
            logger.critical(
                "No master API key configured! API will be insecure. "
                "Set the MCP_CLOUD_API_KEY environment variable."
            )
    
    def authenticate_request(self, request: Request) -> bool:
        """
        Authenticate a request against the master API key.
        
        Args:
            request: The HTTP request to authenticate
            
        Returns:
            True if authentication succeeded, False otherwise
        """
        # If no API key is configured, allow all requests (but log a warning)
        if not self.api_key:
            logger.critical("No API key configured, allowing unauthenticated request. This is INSECURE and should only be used for development.")
            return True
        
        # Get the API key from the request header
        header_key = request.headers.get("X-Master-API-Key")
        
        # Check if the key is valid
        if header_key == self.api_key:
            return True
        else:
            logger.warning("Invalid or missing API key in request")
            return False


@middleware
async def master_auth_middleware(request: Request, handler: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware for authenticating requests with the master API key.
    
    Args:
        request: The HTTP request
        handler: The handler for the request
        
    Returns:
        Response from the handler if authenticated, 401 Unauthorized otherwise
    """
    # Skip authentication for health check
    if request.path == "/health":
        return await handler(request)
    
    # Get the authenticator from the app
    authenticator = request.app["authenticator"]
    
    # Authenticate the request
    if authenticator.authenticate_request(request):
        return await handler(request)
    else:
        # Return 401 Unauthorized if authentication fails
        return web.json_response(
            {"error": "Authentication failed. Invalid or missing API key."},
            status=401
        )