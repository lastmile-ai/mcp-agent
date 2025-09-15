"""Shared utilities for cloud commands."""

from functools import wraps
from typing import Union

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import DEFAULT_API_BASE_URL
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import (
    MCPApp,
    MCPAppClient,
    MCPAppConfiguration,
)


def setup_authenticated_client() -> MCPAppClient:
    """Setup authenticated MCP App client.

    Returns:
        Configured MCPAppClient instance

    Raises:
        CLIError: If authentication fails
    """
    effective_api_key = load_api_key_credentials()

    if not effective_api_key:
        raise CLIError("Must be logged in to access servers. Run 'mcp-agent login'.")

    return MCPAppClient(api_url=DEFAULT_API_BASE_URL, api_key=effective_api_key)


def validate_output_format(format: str) -> None:
    """Validate output format parameter.

    Args:
        format: Output format to validate

    Raises:
        CLIError: If format is invalid
    """
    valid_formats = ["text", "json", "yaml"]
    if format not in valid_formats:
        raise CLIError(
            f"Invalid format '{format}'. Valid options are: {', '.join(valid_formats)}"
        )


def resolve_server(
    client: MCPAppClient, id_or_url: str
) -> Union[MCPApp, MCPAppConfiguration]:
    """Resolve server from ID or URL.

    Args:
        client: Authenticated MCP App client
        id_or_url: Server identifier (app ID, app config ID, or server URL)

    Returns:
        Server object (MCPApp or MCPAppConfiguration)

    Raises:
        CLIError: If server resolution fails
    """
    try:
        return run_async(client.get_app_or_config(id_or_url))

    except Exception as e:
        raise CLIError(f"Failed to resolve server '{id_or_url}': {str(e)}") from e


def handle_server_api_errors(func):
    """Decorator to handle common API errors for server commands.

    Args:
        func: Function to wrap with error handling

    Returns:
        Wrapped function with error handling
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except UnauthenticatedError as e:
            raise CLIError(
                "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
            ) from e
        except CLIError:
            # Re-raise CLIErrors as-is
            raise
        except Exception as e:
            # Get the original function name for better error messages
            func_name = func.__name__.replace("_", " ")
            raise CLIError(f"Error in {func_name}: {str(e)}") from e

    return wrapper


def get_server_name(server: Union[MCPApp, MCPAppConfiguration]) -> str:
    """Get display name for a server.

    Args:
        server: Server object

    Returns:
        Server display name
    """
    if isinstance(server, MCPApp):
        return server.name or "Unnamed"
    else:
        return server.app.name if server.app else "Unnamed"


def get_server_id(server: Union[MCPApp, MCPAppConfiguration]) -> str:
    """Get ID for a server.

    Args:
        server: Server object

    Returns:
        Server ID
    """
    if isinstance(server, MCPApp):
        return server.appId
    else:
        return server.appConfigurationId


def clean_server_status(status: str) -> str:
    """Convert server status from API format to clean format.

    Args:
        status: API status string

    Returns:
        Clean status string
    """
    if status == "APP_SERVER_STATUS_ONLINE":
        return "active"
    elif status == "APP_SERVER_STATUS_OFFLINE":
        return "offline"
    else:
        return "unknown"
