"""User experience utilities for MCP Agent Cloud."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from contextvars import ContextVar

LOG_VERBOSE = ContextVar("log_verbose")

LEFT_COLUMN_WIDTH = 10

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


def _create_label(text: str, style: str) -> str:
    """Create a fixed-width label with style markup."""
    dot = "⏺"
    return f" [{style}]{dot}[/{style}] "


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
        label = _create_label("", "info")
        console.print(f"{label}{message}", *args, **kwargs)
    if log:
        logger.info(message)


def print_verbose(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
):
    """
    Print debug-like verbose content as info only if configured for verbose logging,
    i.e. replaces "if verbose then print_info"
    """
    if LOG_VERBOSE.get():
        print_info(message, *args, log=log, console_output=console_output, **kwargs)


def print_success(
    message: str,
    *args: Any,
    log: bool = True,
    console_output: bool = True,
    **kwargs: Any,
) -> None:
    """Print a success message."""
    if console_output:
        label = _create_label("", "success")
        console.print(f"{label}{message}", *args, **kwargs)
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
        label = _create_label("", "warning")
        console.print(f"{label}{message}", *args, **kwargs)
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
        label = _create_label("", "error")
        console.print(f"{label}{message}", *args, **kwargs)
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
    skipped_secrets = secrets_context.get("skipped_secrets", [])

    return print_secrets_summary(
        deployment_secrets, user_secrets, reused_secrets, skipped_secrets
    )


def print_secrets_summary(
    deployment_secrets: List[Dict[str, str]],
    user_secrets: List[str],
    reused_secrets: Optional[List[Dict[str, str]]] = [],
    skipped_secrets: Optional[List[str]] = [],
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

    # Create a set of reused/skipped secret paths for fast lookup
    reused_paths = (
        {secret["path"] for secret in reused_secrets} if reused_secrets else set()
    )
    skipped_paths = set(skipped_secrets) if skipped_secrets else set()

    for secret in deployment_secrets:
        path = secret["path"]
        handle = secret["handle"]

        if path in reused_paths or path in skipped_paths:
            continue

        # Shorten the handle for display
        short_handle = handle
        if len(handle) > 20:
            short_handle = handle[:8] + "..." + handle[-8:]

        table.add_row("Deployment", path, short_handle, "Created")

    for secret in reused_secrets:
        path = secret["path"]
        handle = secret["handle"]
        short_handle = handle
        if len(handle) > 20:
            short_handle = handle[:8] + "..." + handle[-8:]

        table.add_row("Deployment", path, short_handle, "♻️  Reused")

    for path in skipped_secrets:
        table.add_row("Deployment", path, "⚠️  Skipped", "Error during processing")

    # Add user secrets
    for path in user_secrets:
        table.add_row("User", path, "▶️  Runtime Collection", "End User")

    # Print the table
    console.print()
    console.print(table)
    console.print()

    # Log the summary (without sensitive details)
    reused_count = len(reused_secrets)
    new_deployment_count = len(deployment_secrets)

    logger.info(
        f"Processed {new_deployment_count} new deployment secrets, reused {reused_count} existing secrets, "
        f"and identified {len(user_secrets)} user secrets. Skipped {len(skipped_secrets)} secrets due to errors."
    )

    console.print(
        f"[info]Summary:[/info] {new_deployment_count} new secrets created, {reused_count} existing secrets reused, {len(user_secrets)} user secrets identified, {len(skipped_secrets)} secrets skipped due to errors."
    )


def print_deployment_header(
    app_name: str,
    existing_app_id: Optional[str],
    config_file: Path,
    secrets_file: Optional[Path],
    deployed_secrets_file: Optional[Path],
    deployment_properties_display_info: List[Tuple[str, any, bool]],
) -> None:
    """Print a styled header for the deployment process."""

    deployed_secrets_file_message = "[bright_black]N/A[/bright_black]"
    if deployed_secrets_file:
        deployed_secrets_file_message = f"[cyan]{str(deployed_secrets_file)}[/cyan]"
    elif secrets_file:
        deployed_secrets_file_message = "[cyan]Pending creation[/cyan]"

    secrets_file_message = (
        f"[cyan]{secrets_file}[/cyan]"
        if secrets_file
        else "[bright_black]N/A[/bright_black]"
    )
    app_id_display = (
        f"[ID: {existing_app_id}]"
        if existing_app_id
        else "[bright_yellow][NEW][/bright_yellow]"
    )
    console.print(
        Panel(
            "\n".join(
                [
                    f"App: [cyan]{app_name}[/cyan] {app_id_display}",
                    f"Configuration: [cyan]{config_file}[/cyan]",
                    f"Secrets file: {secrets_file_message}",
                    f"Deployed secrets file: {deployed_secrets_file_message}",
                ]
                + [
                    f"{name}: [{'bright_yellow' if is_changed else 'bright_black'}]{value}[/{'bright_yellow' if is_changed else 'bright_black'}]"
                    for (name, value, is_changed) in deployment_properties_display_info
                ]
            ),
            title="mcp-agent deployment",
            subtitle="LastMile AI",
            border_style="blue",
            expand=False,
        )
    )
    logger.info(f"Starting deployment with configuration: {config_file}")
    logger.info(
        f"Using secrets file: {secrets_file or 'N/A'}, deployed secrets file: {deployed_secrets_file_message}"
    )


def print_configuration_header(
    app_server_url: str,
    required_params: List[str],
    secrets_file: Optional[Path],
    output_file: Optional[Path],
    dry_run: bool,
) -> None:
    """Print a styled header for the configuration process."""
    sections = [
        f"App Server URL: [cyan]{app_server_url}[/cyan]",
    ]

    if required_params:
        sections.append(f"Required secrets: [cyan]{', '.join(required_params)}[/cyan]")
        sections.append(
            f"Secrets file: [cyan]{secrets_file or 'Will prompt for values'}[/cyan]"
        )
        if output_file:
            sections.append(f"Output file: [cyan]{output_file}[/cyan]")
    else:
        sections.append("Required secrets: [bright_black]None[/bright_black]")

    if dry_run:
        sections.append("Mode: [yellow]DRY RUN[/yellow]")

    console.print(
        Panel(
            "\n".join(sections),
            title="mcp-agent configuration",
            subtitle="LastMile AI",
            border_style="blue",
            expand=False,
        )
    )
    logger.info(f"Starting configuration for app: {app_server_url}")
    logger.info(f"Required params: {required_params}")
    logger.info(f"Secrets file: {secrets_file}")
    logger.info(f"Output file: {output_file}")
    logger.info(f"Dry Run: {dry_run}")
