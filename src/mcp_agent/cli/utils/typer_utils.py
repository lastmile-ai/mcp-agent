"""Shared Typer utilities for MCP Agent CLI."""

import logging
import click
from rich.console import Console
from rich.panel import Panel
from typer.core import TyperGroup

from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.utils.ux import print_error


class HelpfulTyperGroup(TyperGroup):
    """Typer group that shows help before usage errors for better UX."""

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            click.echo(ctx.get_help())

            console = Console(stderr=True)
            error_panel = Panel(
                str(e),
                title="Error",
                title_align="left",
                border_style="red",
                expand=True,
            )
            console.print(error_panel)
            ctx.exit(2)

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except CLIError as e:
            # Handle CLIError cleanly - show error message and exit
            logging.error(f"CLI error: {str(e)}")
            print_error(str(e))
            ctx.exit(e.exit_code)
