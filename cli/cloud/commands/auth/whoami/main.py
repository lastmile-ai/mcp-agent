"""MCP Agent Cloud whoami command implementation."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcp_agent.cli.auth import load_credentials, UserCredentials
from mcp_agent.cli.config import settings as _settings
from mcp_agent.cli.exceptions import CLIError


def whoami() -> None:
    """Print current identity and org(s).

    Shows the authenticated user information and organization memberships.
    """
    console = Console()
    credentials = load_credentials()
    # If no stored credentials, allow environment variable key
    if not credentials and _settings.API_KEY:
        credentials = UserCredentials(api_key=_settings.API_KEY)
        # Print a brief note that this is env-based auth
        console.print(
            Panel(
                "Using MCP_API_KEY environment variable for authentication.",
                title="Auth Source",
                border_style="green",
            )
        )
    if not credentials:
        raise CLIError(
            "Not authenticated. Set MCP_API_KEY or run 'mcp-agent login'.",
            exit_code=4,
            retriable=False,
        )

    if credentials.is_token_expired:
        raise CLIError(
            "Authentication token has expired. Use 'mcp-agent login' to re-authenticate.",
            exit_code=4,
            retriable=False,
        )

    user_table = Table(show_header=False, box=None)
    user_table.add_column("Field", style="bold")
    user_table.add_column("Value")

    if credentials.username:
        user_table.add_row("Username", credentials.username)
    if credentials.email:
        user_table.add_row("Email", credentials.email)

    if credentials.token_expires_at:
        user_table.add_row(
            "Token Expires",
            credentials.token_expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    else:
        user_table.add_row("Token Expires", "Never")

    user_panel = Panel(user_table, title="User Information", title_align="left")
    console.print(user_panel)
