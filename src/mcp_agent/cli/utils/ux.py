"""User experience utilities for MCP Agent Cloud."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

# Define a custom theme for consistent styling
CUSTOM_THEME = Theme(
    {
        "info": "bold cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "secret": "bold magenta",
        "env_var": "bold blue",
        "prompt": "bold white on blue",
        "heading": "bold white on blue",
    }
)

# Create console for terminal output
console = Console(theme=CUSTOM_THEME)

logger = logging.getLogger("mcp-agent")


def print_info(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
) -> None:
    """Print an informational message.

    Args:
        message: The message to print
        log: Whether to log to file
        console_output: Whether to print to console
    """
    if console_output:
        console.print(f"[info]INFO:[/info] {message}", *args, **kwargs)
    if log:
        logger.info(message)


def print_success(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
) -> None:
    """Print a success message."""
    if console_output:
        console.print(f"[success]SUCCESS:[/success] {message}", *args, **kwargs)
    if log:
        logger.info(f"SUCCESS: {message}")


def print_warning(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
) -> None:
    """Print a warning message."""
    if console_output:
        console.print(f"[warning]WARNING:[/warning] {message}", *args, **kwargs)
    if log:
        logger.warning(message)


def print_error(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
) -> None:
    """Print an error message."""
    if console_output:
        console.print(f"[error]ERROR:[/error] {message}", *args, **kwargs)
    if log:
        logger.error(message, exc_info=True)


def print_secret_summary(secrets_context: Dict[str, Any]) -> None:
    """Print a summary of processed secrets from context.

    Args:
        secrets_context: Dictionary containing info about processed secrets
    """
    deployment_secrets = secrets_context.get("deployment_secrets", [])
    user_secrets = secrets_context.get("user_secrets", [])
    reused_secrets = secrets_context.get("reused_secrets", [])

    return print_secrets_summary(deployment_secrets, user_secrets, reused_secrets)


def print_secrets_summary(
    deployment_secrets: List[Dict[str, str]],
    user_secrets: List[str],
    reused_secrets: Optional[List[Dict[str, str]]] = None,
) -> None:
    """Print a summary table of processed secrets."""
    # Create the table
    table = Table(
        title="[heading]Secrets Processing Summary[/heading]",
        expand=False,
        border_style="blue",
    )

    # Add columns
    table.add_column("Type", style="cyan", justify="center")
    table.add_column("Path", style="bright_blue")
    table.add_column("Handle/Status", style="green", no_wrap=True)
    table.add_column("Source", style="yellow", justify="center")

    # Initialize reused_secrets if not provided
    if reused_secrets is None:
        reused_secrets = []

    # Create a set of reused secret paths for fast lookup
    reused_paths = {secret["path"] for secret in reused_secrets}

    # Add deployment secrets
    for secret in deployment_secrets:
        path = secret["path"]
        handle = secret["handle"]

        # Skip if already handled as a reused secret
        if path in reused_paths:
            continue

        # Shorten the handle for display
        short_handle = handle
        if len(handle) > 20:
            short_handle = handle[:8] + "..." + handle[-8:]

        table.add_row("Deployment", path, short_handle)

    # Add reused secrets
    for secret in reused_secrets:
        path = secret["path"]
        handle = secret["handle"]

        # Shorten the handle for display
        short_handle = handle
        if len(handle) > 20:
            short_handle = handle[:8] + "..." + handle[-8:]

        table.add_row("Deployment", path, short_handle, "♻️ Reused")

    # Add user secrets
    for path in user_secrets:
        table.add_row("User", path, "▶️ Runtime Collection", "End User")

    # Print the table
    console.print()
    console.print(table)
    console.print()

    # Log the summary (without sensitive details)
    reused_count = len(reused_secrets)
    new_deployment_count = len(deployment_secrets)

    logger.info(
        f"Processed {new_deployment_count} new deployment secrets, reused {reused_count} existing secrets, "
        f"and identified {len(user_secrets)} user secrets"
    )

    console.print(
        f"[info]Summary:[/info] {new_deployment_count} new secrets created, {reused_count} existing secrets reused"
    )


def print_deployment_header(
    app_name: str,
    app_id: str,
    config_file: Path,
    secrets_file: Optional[Path] = None,
    deployed_secrets_file: Optional[Path] = None,
) -> None:
    """Print a styled header for the deployment process."""
    console.print(
        Panel(
            f"App: [cyan]{app_name}[/cyan] (ID: [cyan]{app_id}[/cyan])\n"
            f"Configuration: [cyan]{config_file}[/cyan]\n"
            f"Secrets file: [cyan]{secrets_file or 'N/A'}[/cyan]\n"
            f"Deployed secrets file: [cyan]{deployed_secrets_file or 'Pending creation'}[/cyan]\n",
            title="MCP Agent Deployment",
            subtitle="LastMile AI",
            border_style="blue",
            expand=False,
        )
    )
    logger.info(f"Starting deployment with configuration: {config_file}")
    logger.info(
        f"Using secrets file: {secrets_file or 'N/A'}, deployed secrets file: {deployed_secrets_file or 'Pending creation'}"
    )


def print_configuration_header(
    secrets_file: Optional[Path], output_file: Optional[Path], dry_run: bool
) -> None:
    """Print a styled header for the configuration process."""
    console.print(
        Panel(
            f"Secrets file: [cyan]{secrets_file or 'Not specified'}[/cyan]\n"
            f"Output file: [cyan]{output_file or 'Not specified'}[/cyan]\n"
            f"Mode: [{'yellow' if dry_run else 'green'}]{'DRY RUN' if dry_run else 'CONFIGURE'}[/{'yellow' if dry_run else 'green'}]",
            title="MCP APP Configuration",
            border_style="blue",
            expand=False,
        )
    )
    logger.info(f"Starting configuration with secrets file: {secrets_file}")
    logger.info(f"Output file: {output_file}")
    logger.info(f"Dry Run: {dry_run}")
