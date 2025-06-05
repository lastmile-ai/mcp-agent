"""MCP Agent Cloud CLI entry point."""

import typer
from typing import Optional

from .. import __version__
from ..commands import (
    deploy_config,
    login,
)
from ..commands.apps import list_apps

# Root typer for `mcp-agent` CLI commands
app = typer.Typer(help="MCP Agent Cloud CLI for deployment and management")

# Simply wrap the function with typer to preserve its signature
app.command(name="deploy")(deploy_config)
app.command(name="login")(login)

# Sub-typer for `mcp-agent apps` commands
app_cmd_apps = typer.Typer(help="Management commands for multiple MCP Apps")
app_cmd_apps.command(name="list")(list_apps)
app.add_typer(app_cmd_apps, name="apps", help="Manage MCP Apps")


@app.callback()
def callback(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit", is_flag=True
    ),
) -> None:
    """MCP Agent Cloud CLI."""
    if version:
        typer.echo(f"MCP Agent Cloud CLI version: {__version__}")
        raise typer.Exit()


def run() -> None:
    """Run the CLI application."""
    app()


if __name__ == "__main__":
    run()
