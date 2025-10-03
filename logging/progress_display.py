"""
Centralized progress display configuration for MCP Agent.
Provides optional shared progress display instance for consistent progress handling.
"""

from typing import Optional
from mcp_agent.console import console
from mcp_agent.logging.rich_progress import RichProgressDisplay

# Main progress display instance - can be created when needed
progress_display: Optional[RichProgressDisplay] = None


def get_progress_display(token_counter=None) -> RichProgressDisplay:
    """Get or create the shared progress display instance.

    Args:
        token_counter: Optional TokenCounter instance for token tracking
    """
    global progress_display
    if progress_display is None:
        progress_display = RichProgressDisplay(console, token_counter)
    return progress_display


def create_progress_display(token_counter=None) -> RichProgressDisplay:
    """Create a new progress display instance.

    Args:
        token_counter: Optional TokenCounter instance for token tracking
    """
    return RichProgressDisplay(console, token_counter)
