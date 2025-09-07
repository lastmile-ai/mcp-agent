"""MCP Agent Cloud whoami command implementation."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcp_agent.cli.auth import load_credentials
from mcp_agent.cli.exceptions import CLIError


def whoami() -> None:
    """Print current identity and org(s).

    Shows the authenticated user information and organization memberships.
    """
    credentials = load_credentials()

    if not credentials:
        raise CLIError(
            "Not logged in. Use 'mcp-agent login' to authenticate.", exit_code=4
        )

    if credentials.is_token_expired:
        raise CLIError(
            "Authentication token has expired. Use 'mcp-agent login' to re-authenticate.",
            exit_code=4,
        )

    console = Console()

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
