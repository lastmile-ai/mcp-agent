"""MCP Agent Cloud logout command implementation."""

from rich.prompt import Confirm

from mcp_agent.cli.auth import clear_credentials, load_credentials
from mcp_agent.cli.utils.ux import print_info, print_success


def logout() -> None:
    """Clear credentials.

    Removes stored authentication information.
    """
    credentials = load_credentials()

    if not credentials:
        print_info("Not currently logged in.")
        return

    user_info = "current user"
    if credentials.username:
        user_info = f"user '{credentials.username}'"
    elif credentials.email:
        user_info = f"user '{credentials.email}'"

    if not Confirm.ask(f"Are you sure you want to logout {user_info}?", default=False):
        print_info("Logout cancelled.")
        return

    if clear_credentials():
        print_success("Successfully logged out.")
    else:
        print_info("No credentials were found to clear.")
