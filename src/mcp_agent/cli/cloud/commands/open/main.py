"""Open MCP Agent Cloud portal in browser."""

import webbrowser
from typing import Optional

import typer

from mcp_agent.cli.core.constants import DEFAULT_BASE_URL
from mcp_agent.cli.utils.ux import print_info, print_warning


def open_portal(
    server: Optional[str] = typer.Option(
        None,
        "--server",
        help="Server ID or URL to open deployment details page",
    ),
) -> None:
    """Open the MCP Agent Cloud portal in browser.

    Opens the portal home page by default, or the deployment details page
    if a server ID or URL is provided.

    Args:
        server: Optional server ID or URL to open deployment details for
    """
    # Use the base URL directly for portal access
    base_url = DEFAULT_BASE_URL.rstrip("/")

    if server:
        if server.startswith("http"):
            # If it's a URL, try to extract server ID
            url = f"{base_url}/deployments/{server.split('/')[-1]}"
            print_info(f"Opening deployment details for server: {server}")
        else:
            # If it's an ID, construct the deployment page URL
            url = f"{base_url}/deployments/{server}"
            print_info(f"Opening deployment details for server ID: {server}")
    else:
        url = f"{base_url}/dashboard"
        print_info("Opening MCP Agent Cloud portal")

    try:
        webbrowser.open(url)
        print_info(f"Portal opened at: {url}")
    except Exception as e:
        print_warning(f"Could not open browser automatically: {str(e)}")
        print_info(f"Please open this URL manually: {url}")
