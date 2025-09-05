import asyncio
from typing import Optional, Tuple

import httpx

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.auth import UserCredentials
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL


def run_async(coro):
    """
    Simple helper to run an async coroutine from synchronous code.

    This properly handles the event loop setup in all contexts:
    - Normal application usage
    - Within tests that use pytest-asyncio
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # If we're already in an event loop (like in pytest-asyncio tests)
        if "cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        raise


def parse_app_identifier(identifier: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse app identifier to extract app ID and config ID.
    
    Args:
        identifier: App identifier (must be app_... or apcnf_...)
        
    Returns:
        Tuple of (app_id, config_id)
        
    Raises:
        ValueError: If identifier format is not recognized
    """
    
    if identifier.startswith('apcnf_'):
        return None, identifier
    
    if identifier.startswith('app_'):
        return identifier, None
    
    raise ValueError(f"Invalid identifier format: '{identifier}'. Must be an app ID (app_...) or app configuration ID (apcnf_...)")


async def resolve_server_url(
    app_id: Optional[str],
    config_id: Optional[str], 
    credentials: UserCredentials,
) -> str:
    """Resolve server URL from app ID or configuration ID."""
    
    if not app_id and not config_id:
        raise CLIError("Either app_id or config_id must be provided")
    
    if app_id:
        endpoint = "/mcp_app/get_app"
        payload = {"app_id": app_id}
        response_key = "app"
        not_found_msg = f"App '{app_id}' not found"
        not_deployed_msg = f"App '{app_id}' is not deployed yet"
        no_url_msg = f"No server URL found for app '{app_id}'"
        offline_msg = f"App '{app_id}' server is offline"
        api_error_msg = "Failed to get app info"
    else:
        endpoint = "/mcp_app/get_app_configuration"
        payload = {"app_configuration_id": config_id}
        response_key = "appConfiguration"
        not_found_msg = f"App configuration '{config_id}' not found"
        not_deployed_msg = f"App configuration '{config_id}' is not deployed yet"
        no_url_msg = f"No server URL found for app configuration '{config_id}'"
        offline_msg = f"App configuration '{config_id}' server is offline"
        api_error_msg = "Failed to get app configuration"
    
    api_base = DEFAULT_API_BASE_URL
    headers = {
        "Authorization": f"Bearer {credentials.api_key}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{api_base}{endpoint}", json=payload, headers=headers)
            
            if response.status_code == 404:
                raise CLIError(not_found_msg)
            elif response.status_code != 200:
                raise CLIError(f"{api_error_msg}: {response.status_code} {response.text}")
            
            data = response.json()
            resource_info = data.get(response_key, {})
            server_info = resource_info.get("appServerInfo")
            
            if not server_info:
                raise CLIError(not_deployed_msg)
            
            server_url = server_info.get("serverUrl")
            if not server_url:
                raise CLIError(no_url_msg)
                
            status = server_info.get("status", "APP_SERVER_STATUS_UNSPECIFIED")
            if status == "APP_SERVER_STATUS_OFFLINE":
                raise CLIError(offline_msg)
            
            return server_url
                
    except httpx.RequestError as e:
        raise CLIError(f"Failed to connect to API: {e}")
