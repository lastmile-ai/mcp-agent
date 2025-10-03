import asyncio
from typing import Optional

import typer
from rich.prompt import Confirm, Prompt

from mcp_agent.cli.auth import (
    UserCredentials,
    load_credentials,
    save_credentials,
)
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import APIClient
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import (
    print_info,
    print_success,
    print_warning,
)

from .constants import DEFAULT_API_AUTH_PATH


def _load_user_credentials(api_key: str) -> UserCredentials:
    """Load credentials with user profile data fetched from API.

    Args:
        api_key: The API key

    Returns:
        UserCredentials object with profile data if available
    """

    async def fetch_profile() -> UserCredentials:
        """Fetch user profile from the API."""
        client = APIClient(settings.API_BASE_URL, api_key)

        response = await client.post("user/get_profile", {})
        user_data = response.json()

        user_profile = user_data.get("user", {})

        return UserCredentials(
            api_key=api_key,
            username=user_profile.get("name"),
            email=user_profile.get("email"),
        )

    try:
        return asyncio.run(fetch_profile())
    except Exception as e:
        print_warning(f"Could not fetch user profile: {str(e)}")
        # Fallback to minimal credentials
        return UserCredentials(api_key=api_key)


def login(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Optionally set an existing API key to use for authentication, bypassing manual login.",
        envvar="MCP_API_KEY",
    ),
    no_open: bool = typer.Option(
        False,
        "--no-open",
        help="Don't automatically open browser for authentication.",
    ),
) -> str:
    """Authenticate to MCP Agent Cloud API.

    Direct to the api keys page for obtaining credentials, routing through login.

    Args:
        api_key: Optionally set an existing API key to use for authentication, bypassing manual login.
        no_open: Don't automatically open browser for authentication.

    Returns:
        API key string. Prints success message if login is successful.
    """

    existing_credentials = load_credentials()
    if existing_credentials and not existing_credentials.is_token_expired:
        if not Confirm.ask("You are already logged in. Do you want to login again?"):
            print_info("Using existing credentials.")
            return existing_credentials.api_key

    if api_key:
        print_info("Using provided API key for authentication (MCP_API_KEY).")
        if not _is_valid_api_key(api_key):
            raise CLIError("Invalid API key provided.", retriable=False)

        credentials = _load_user_credentials(api_key)

        save_credentials(credentials)
        print_success("API key set.")
        if credentials.username:
            print_info(f"Logged in as: {credentials.username}")
        return api_key

    base_url = settings.API_BASE_URL

    return _handle_browser_auth(base_url, no_open)


def _handle_browser_auth(base_url: str, no_open: bool) -> str:
    """Handle browser-based authentication flow.

    Args:
        base_url: API base URL
        no_open: Whether to skip automatic browser opening

    Returns:
        API key string
    """
    auth_url = f"{base_url}/{DEFAULT_API_AUTH_PATH}"

    # TODO: This flow should be updated to OAuth2. Probably need to spin up local server to handle
    # the oauth2 callback url.
    if not no_open:
        print_info("Opening MCP Agent Cloud API login in browser...")
        print_info(
            f"If the browser doesn't automatically open, you can manually visit: {auth_url}"
        )
        typer.launch(auth_url)
    else:
        print_info(f"Please visit: {auth_url}")

    return _handle_manual_key_input()


def _handle_manual_key_input() -> str:
    """Handle manual API key input.

    Returns:
        API key string
    """
    input_api_key = Prompt.ask("Please enter your API key :key:")

    if not input_api_key:
        print_warning("No API key provided.")
        raise CLIError("Failed to set valid API key", retriable=False)

    if not _is_valid_api_key(input_api_key):
        print_warning("Invalid API key provided.")
        raise CLIError("Failed to set valid API key", retriable=False)

    credentials = _load_user_credentials(input_api_key)

    save_credentials(credentials)
    print_success("API key set.")
    if credentials.username:
        print_info(f"Logged in as: {credentials.username}")

    return input_api_key


def _is_valid_api_key(api_key: str) -> bool:
    """Validate the API key.

    Args:
        api_key: The API key to validate.

    Returns:
        bool: True if the API key is valid, False otherwise.
    """
    return api_key.startswith("lm_mcp_api_")
