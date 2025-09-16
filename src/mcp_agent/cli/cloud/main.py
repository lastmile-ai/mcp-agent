"""MCP Agent Cloud CLI entry point."""

import logging
import os
from importlib.metadata import version as metadata_version
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import typer

from mcp_agent.cli.cloud.commands import (
    configure_app,
    deploy_config,
    login,
    logout,
    whoami,
)
from mcp_agent.cli.cloud.commands.app import (
    delete_app,
    get_app_status,
    list_app_workflows,
)
from mcp_agent.cli.cloud.commands.logger import tail_logs
from mcp_agent.cli.cloud.commands.servers import (
    delete_server,
    describe_server,
    list_servers,
)
from mcp_agent.cli.cloud.commands.workflows import (
    cancel_workflow,
    describe_workflow,
    list_workflow_runs,
    list_workflows,
    resume_workflow,
    suspend_workflow,
)
from mcp_agent.cli.utils.typer_utils import HelpfulTyperGroup
from mcp_agent.cli.utils.ux import print_error
from mcp_agent.cli.utils.version_check import maybe_warn_newer_version

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
    help="MCP Agent Cloud CLI for deployment and management",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)

# Simply wrap the function with typer to preserve its signature
app.command(
    name="configure",
    help="Configure an MCP app with the required params (e.g. user secrets).",
)(configure_app)


# Deployment command
app.command(name="deploy", help="Deploy an MCP agent (alias for 'cloud deploy')")(
    deploy_config
)

# Sub-typer for `mcp-agent app` commands
app_cmd_app = typer.Typer(
    help="Management commands for an MCP App",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)
app_cmd_app.command(name="list")(list_servers)
app_cmd_app.command(name="delete")(delete_app)
app_cmd_app.command(name="status")(get_app_status)
app_cmd_app.command(name="workflows")(list_app_workflows)
app.add_typer(app_cmd_app, name="apps", help="Manage an MCP App")

# Sub-typer for `mcp-agent workflows` commands
app_cmd_workflows = typer.Typer(
    help="Management commands for MCP Workflows",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)
app_cmd_workflows.command(name="describe")(describe_workflow)
app_cmd_workflows.command(
    name="status", help="Describe a workflow execution (alias for 'describe')"
)(describe_workflow)
app_cmd_workflows.command(name="resume")(resume_workflow)
app_cmd_workflows.command(name="suspend")(suspend_workflow)
app_cmd_workflows.command(name="cancel")(cancel_workflow)
app_cmd_workflows.command(name="list")(list_workflows)
app_cmd_workflows.command(name="runs")(list_workflow_runs)

# Sub-typer for `mcp-agent servers` commands
app_cmd_servers = typer.Typer(
    help="Management commands for MCP Servers",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)
app_cmd_servers.command(name="list")(list_servers)
app_cmd_servers.command(name="describe")(describe_server)
app_cmd_servers.command(name="delete")(delete_server)
app_cmd_servers.command(
    name="workflows",
    help="List available workflows for a server (alias for 'workflows list')",
)(list_workflows)
app.add_typer(app_cmd_servers, name="servers", help="Manage MCP Servers")

# Sub-typer for `mcp-agent cloud auth` commands
app_cmd_cloud_auth = typer.Typer(
    help="Cloud authentication commands",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)
# Register auth commands under cloud auth
app_cmd_cloud_auth.command(
    name="login",
    help="""
Authenticate to MCP Agent Cloud API.\n\n
Direct to the api keys page for obtaining credentials, routing through login.
""".strip(),
)(login)
app_cmd_cloud_auth.command(name="whoami", help="Print current identity and org(s).")(
    whoami
)
app_cmd_cloud_auth.command(name="logout", help="Clear credentials.")(logout)
# Sub-typer for `mcp-agent cloud logger` commands
app_cmd_cloud_logger = typer.Typer(
    help="Log configuration and streaming commands",
    no_args_is_help=True,
    cls=HelpfulTyperGroup,
)
# Register logger commands under cloud logger
app_cmd_cloud_logger.command(
    name="tail",
    help="Retrieve and stream logs from deployed MCP apps",
)(tail_logs)

# Add sub-typers directly to app (which is the cloud namespace when mounted)
app.add_typer(app_cmd_cloud_auth, name="auth", help="Authentication commands")
app.add_typer(app_cmd_cloud_logger, name="logger", help="Logging and observability")
app.add_typer(app_cmd_workflows, name="workflows", help="Workflow management commands")
# Top-level auth commands that map to cloud auth commands
app.command(
    name="login",
    help="""
Authenticate to MCP Agent Cloud API.\n\n
Direct to the api keys page for obtaining credentials, routing through login.
""".strip(),
)(login)
app.command(name="whoami", help="Print current identity and org(s).")(whoami)
app.command(name="logout", help="Clear credentials.")(logout)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit", is_flag=True
    ),
) -> None:
    """MCP Agent Cloud CLI."""
    # Best-effort version check (5s timeout, non-fatal). Guard to run once.
    try:
        maybe_warn_newer_version()
    except Exception:
        pass
    if version:
        v = metadata_version("mcp-agent")
        typer.echo(f"MCP Agent Cloud CLI version: {v}")
        raise typer.Exit()


def run() -> None:
    """Run the CLI application."""
    try:
        # Run best-effort version check before Typer may early-exit on --help
        try:
            maybe_warn_newer_version()
        except Exception:
            pass
        app()
    except Exception as e:
        # Unexpected errors - log full exception and show clean error to user
        logging.exception("Unhandled exception in CLI")
        print_error(f"An unexpected error occurred: {str(e)}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    run()
