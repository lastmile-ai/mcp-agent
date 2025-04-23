"""User experience utilities for MCP Agent Cloud."""

from typing import Any, Optional
from rich.console import Console

console = Console()


def print_info(message: str, *args: Any, **kwargs: Any) -> None:
    """Print an informational message."""
    console.print(f"[blue]INFO:[/blue] {message}", *args, **kwargs)


def print_success(message: str, *args: Any, **kwargs: Any) -> None:
    """Print a success message."""
    console.print(f"[green]SUCCESS:[/green] {message}", *args, **kwargs)


def print_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """Print a warning message."""
    console.print(f"[yellow]WARNING:[/yellow] {message}", *args, **kwargs)


def print_error(message: str, *args: Any, **kwargs: Any) -> None:
    """Print an error message."""
    console.print(f"[red]ERROR:[/red] {message}", *args, **kwargs)