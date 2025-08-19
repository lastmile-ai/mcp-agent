"""MCP Agent Cloud CLI entry point."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import typer

from mcp_agent_cloud import __version__
from mcp_agent_cloud.commands import configure_app, deploy_config, login
from mcp_agent_cloud.commands.app import delete_app, get_app_status, list_app_workflows
from mcp_agent_cloud.commands.apps import list_apps
from mcp_agent_cloud.commands.workflow import get_workflow_status

# Setup file logging
LOG_DIR = Path.home() / ".mcp-agent" / "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = LOG_DIR / "mcp-agent.log"

# Configure separate file logging without console output
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

# Configure logging - only sending to file, not to console
logging.basicConfig(level=logging.INFO, handlers=[file_handler])

# Root typer for `mcp-agent` CLI commands
app = typer.Typer(
    help="MCP Agent Cloud CLI for deployment and management", no_args_is_help=True
)

# Simply wrap the function with typer to preserve its signature
app.command(name="configure")(configure_app)
app.command(name="deploy")(deploy_config)
app.command(name="login")(login)

# Sub-typer for `mcp-agent apps` commands
app_cmd_apps = typer.Typer(
    help="Management commands for multiple MCP Apps", no_args_is_help=True
)
app_cmd_apps.command(name="list")(list_apps)
app.add_typer(app_cmd_apps, name="apps", help="Manage MCP Apps")

# Sub-typer for `mcp-agent app` commands
app_cmd_app = typer.Typer(
    help="Management commands for an MCP App", no_args_is_help=True
)
app_cmd_app.command(name="delete")(delete_app)
app_cmd_app.command(name="status")(get_app_status)
app_cmd_app.command(name="workflows")(list_app_workflows)
app.add_typer(app_cmd_app, name="app", help="Manage an MCP App")

# Sub-typer for `mcp-agent workflow` commands
app_cmd_workflow = typer.Typer(
    help="Management commands for MCP Workflows", no_args_is_help=True
)
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
