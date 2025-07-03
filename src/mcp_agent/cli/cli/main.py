"""MCP Agent Cloud CLI entry point."""

import typer
from typing import Optional

from .. import __version__
from ..commands import (
    configure_app,
    deploy_config,
    login,
)
from ..commands.app import (
    delete_app,
    get_app_status,
    list_app_workflows,
)
from ..commands.apps import list_apps
from ..commands.workflow import get_workflow_status

# Root typer for `mcp-agent` CLI commands
app = typer.Typer(help="MCP Agent Cloud CLI for deployment and management")

# Simply wrap the function with typer to preserve its signature
app.command(name="configure")(configure_app)
app.command(name="deploy")(deploy_config)
app.command(name="login")(login)

# Sub-typer for `mcp-agent apps` commands
app_cmd_apps = typer.Typer(help="Management commands for multiple MCP Apps")
app_cmd_apps.command(name="list")(list_apps)
app.add_typer(app_cmd_apps, name="apps", help="Manage MCP Apps")

# Sub-typer for `mcp-agent app` commands
app_cmd_app = typer.Typer(help="Management commands for an MCP App")
app_cmd_app.command(name="delete")(delete_app)
app_cmd_app.command(name="status")(get_app_status)
app_cmd_app.command(name="workflows")(list_app_workflows)
app.add_typer(app_cmd_app, name="app", help="Manage an MCP App")

# Sub-typer for `mcp-agent workflow` commands
app_cmd_workflow = typer.Typer(help="Management commands for MCP Workflows")
app_cmd_workflow.command(name="status")(get_workflow_status)
app.add_typer(app_cmd_workflow, name="workflow", help="Manage MCP Workflows")


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
