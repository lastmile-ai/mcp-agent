"""User experience utilities for MCP Agent Cloud."""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.logging import RichHandler
import logging
from logging.handlers import RotatingFileHandler

# Define a custom theme for consistent styling
CUSTOM_THEME = Theme({
    "info": "bold cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "secret": "bold magenta",
    "env_var": "bold blue",
    "prompt": "bold white on blue",
    "heading": "bold white on blue",
})

# Create console for terminal output
console = Console(theme=CUSTOM_THEME)

# Setup file logging
LOG_DIR = Path.home() / ".mcp-agent" / "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = LOG_DIR / "mcp-agent.log"

# Configure separate file logging without console output
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

# Configure logging - only sending to file, not to console
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler]
)

logger = logging.getLogger("mcp-agent")


def print_info(message: str, *args: Any, log: bool = True, console_output: bool = True, **kwargs: Any) -> None:
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


def print_success(message: str, *args: Any, log: bool = True, console_output: bool = True, **kwargs: Any) -> None:
    """Print a success message."""
    if console_output:
        console.print(f"[success]SUCCESS:[/success] {message}", *args, **kwargs)
    if log:
        logger.info(f"SUCCESS: {message}")


def print_warning(message: str, *args: Any, log: bool = True, console_output: bool = True, **kwargs: Any) -> None:
    """Print a warning message."""
    if console_output:
        console.print(f"[warning]WARNING:[/warning] {message}", *args, **kwargs)
    if log:
        logger.warning(message)


def print_error(message: str, *args: Any, log: bool = True, console_output: bool = True, **kwargs: Any) -> None:
    """Print an error message."""
    if console_output:
        console.print(f"[error]ERROR:[/error] {message}", *args, **kwargs)
    if log:
        logger.error(message)


def print_secret_prompt(env_var: str, path: str) -> None:
    """Print a styled prompt for a secret value."""
    console.print(Panel(
        f"Environment variable [env_var]{env_var}[/env_var] not found.\n"
        f"This is needed for the secret at [secret]{path}[/secret]",
        title="Secret Required",
        border_style="yellow",
        expand=False
    ))


def print_secret_summary(secrets_context: Dict[str, Any]) -> None:
    """Print a summary of processed secrets from context.
    
    Args:
        secrets_context: Dictionary containing info about processed secrets
    """
    dev_secrets = secrets_context.get('developer_secrets', [])
    user_secrets = secrets_context.get('user_secrets', [])
    env_loaded = secrets_context.get('env_loaded', [])
    prompted = secrets_context.get('prompted', [])
    
    return print_secrets_summary(dev_secrets, user_secrets, env_loaded, prompted)


def print_secrets_summary(
    dev_secrets: List[Dict[str, str]], 
    user_secrets: List[str],
    env_loaded: List[str],
    prompted: List[str]
) -> None:
    """Print a summary table of processed secrets."""
    # Create the table
    table = Table(
        title="[heading]Secrets Processing Summary[/heading]", 
        expand=False,
        border_style="blue"
    )
    
    # Add columns
    table.add_column("Type", style="cyan", justify="center")
    table.add_column("Path", style="bright_blue")
    table.add_column("Handle/Status", style="green", no_wrap=True)
    table.add_column("Source", style="yellow", justify="center")
    
    # Add developer secrets
    for secret in dev_secrets:
        path = secret['path']
        handle = secret['handle']
        if path in env_loaded:
            source = "✓ Environment"
        elif path in prompted:
            source = "✏️  User Input"
        else:
            source = "User Input"
        
        # Shorten the handle for display
        short_handle = handle
        if len(handle) > 20:
            short_handle = handle[:8] + "..." + handle[-8:]
            
        table.add_row("Developer", path, short_handle, source)
    
    # Add user secrets
    for path in user_secrets:
        table.add_row("User", path, "▶️ Runtime Collection", "End User")
    
    # Print the table
    console.print()
    console.print(table)
    console.print()
    
    # Log the summary (without sensitive details)
    logger.info(f"Processed {len(dev_secrets)} developer secrets and identified {len(user_secrets)} user secrets")
    
    if prompted:
        logger.info(f"User was prompted for {len(prompted)} secrets: {', '.join(prompted)}")


def print_deployment_header(config_file: Path, secrets_file: Path, dry_run: bool) -> None:
    """Print a styled header for the deployment process."""
    console.print(Panel(
        f"Configuration: [cyan]{config_file}[/cyan]\n"
        f"Secrets file: [cyan]{secrets_file}[/cyan]\n"
        f"Mode: [{'yellow' if dry_run else 'green'}]{'DRY RUN' if dry_run else 'DEPLOY'}[/{'yellow' if dry_run else 'green'}]",
        title="MCP Agent Deployment",
        subtitle="LastMile AI",
        border_style="blue",
        expand=False
    ))
    logger.info(f"Starting deployment with configuration: {config_file}")
    logger.info(f"Using secrets file: {secrets_file}")
    logger.info(f"Dry Run: {dry_run}")