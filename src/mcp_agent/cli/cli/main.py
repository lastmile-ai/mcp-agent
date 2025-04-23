"""MCP Agent Cloud CLI entry point."""

import typer
from typing import Optional

from .. import __version__
from ..commands import deploy_config

app = typer.Typer(help="MCP Agent Cloud CLI for deployment and management")

# Simply wrap the function with typer to preserve its signature
app.command(name="deploy")(deploy_config)


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