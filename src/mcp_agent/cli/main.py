"""
Top-level CLI entrypoint for mcp-agent (non-cloud + cloud groups).

Uses Typer and Rich. This module wires together all non-cloud command groups
and mounts the existing cloud CLI under the `cloud` namespace. Initial
implementation provides scaffolding; individual commands can be implemented
progressively.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

from mcp_agent.cli.utils.ux import print_error
from mcp_agent.cli.utils.version_check import maybe_warn_newer_version

# Mount existing cloud CLI
try:
    from mcp_agent.cli.cloud.main import app as cloud_app  # type: ignore
except Exception:  # pragma: no cover - cloud is optional for non-cloud development
    cloud_app = typer.Typer(help="Cloud commands (unavailable)")


# Local command groups (scaffolded)
from mcp_agent.cli.cloud.commands import deploy_config, login
from mcp_agent.cli.commands import (
    check as check_cmd,
    chat as chat_cmd,
    dev as dev_cmd,
    invoke as invoke_cmd,
    serve as serve_cmd,
    server as server_cmd,
    build as build_cmd,
    logs as logs_cmd,
    doctor as doctor_cmd,
    configure as configure_cmd,
)
from mcp_agent.cli.commands import (
    config as config_cmd,
)
from mcp_agent.cli.commands import (
    go as go_cmd,
)
from mcp_agent.cli.commands import (
    init as init_cmd,
)
from mcp_agent.cli.commands import (
    keys as keys_cmd,
)
from mcp_agent.cli.commands import (
    models as models_cmd,
)
from mcp_agent.cli.commands import (
    quickstart as quickstart_cmd,
)
from mcp_agent.cli.utils.typer_utils import HelpfulTyperGroup

app = typer.Typer(
    help="mcp-agent CLI",
    add_completion=True,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=HelpfulTyperGroup,
)

# Local development umbrella group
dev_group = typer.Typer(
    help="Local development: start app, chat, invoke, serve, servers, build, logs",
    no_args_is_help=False,
    cls=HelpfulTyperGroup,
)


@dev_group.callback(invoke_without_command=True)
def _dev_group_entry(
    ctx: typer.Context,
    script: Path = typer.Option(None, "--script", help="Entry script"),
):
    """If no subcommand is provided, behave like 'dev start'."""
    if ctx.invoked_subcommand:
        return
    # Delegate to the existing dev implementation
    dev_cmd.dev(script=script)


console = Console(stderr=False)
err_console = Console(stderr=True)


def _print_version() -> None:
    try:
        import importlib.metadata as _im

        ver = _im.version("mcp-agent")
    except Exception:
        ver = "unknown"
    console.print(f"mcp-agent {ver}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Reduce output"),
    color: bool = typer.Option(
        True, "--color/--no-color", help="Enable/disable color output"
    ),
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format for list/describe commands",
        show_default=True,
        case_sensitive=False,
    ),
) -> None:
    """mcp-agent command line interface."""
    # Persist global options on context for subcommands
    ctx.obj = {
        "verbose": verbose,
        "quiet": quiet,
        "color": color,
        "format": format.lower(),
    }

    if not color:
        # Disable colors globally for both std and err consoles
        console.no_color = True
        err_console.no_color = True

    if version:
        _print_version()
        raise typer.Exit(0)

    # If no subcommand given, show brief overview
    if ctx.invoked_subcommand is None:
        console.print("mcp-agent - Model Context Protocol agent CLI\n")
        console.print("Run 'mcp-agent --help' to see all commands.")

    # Best-effort version check (5s timeout, non-fatal)
    try:
        maybe_warn_newer_version()
    except Exception:
        pass


# Mount non-cloud command groups (top-level, curated)
app.add_typer(init_cmd.app, name="init", help="Scaffold a new mcp-agent project")
app.add_typer(quickstart_cmd.app, name="quickstart", help="Copy curated examples")
app.add_typer(config_cmd.app, name="config", help="Manage and inspect configuration")
app.add_typer(doctor_cmd.app, name="doctor", help="Comprehensive diagnostics")

# Group local dev/runtime commands under `dev`
dev_group.add_typer(dev_cmd.app, name="start", help="Run app locally with live reload")
dev_group.add_typer(
    chat_cmd.app, name="chat", help="Ephemeral REPL for quick iteration"
)
dev_group.add_typer(
    invoke_cmd.app, name="invoke", help="Invoke agent/workflow programmatically"
)
dev_group.add_typer(serve_cmd.app, name="serve", help="Serve app as an MCP server")
dev_group.add_typer(server_cmd.app, name="server", help="Local server helpers")
dev_group.add_typer(
    build_cmd.app, name="build", help="Preflight and bundle prep for deployment"
)
dev_group.add_typer(logs_cmd.app, name="logs", help="Tail local logs")
dev_group.add_typer(
    check_cmd.app, name="check", help="Check configuration and environment"
)
dev_group.add_typer(go_cmd.app, name="go", help="Quick interactive agent")
dev_group.add_typer(keys_cmd.app, name="keys", help="Manage provider API keys")
dev_group.add_typer(models_cmd.app, name="models", help="List and manage models")
dev_group.add_typer(configure_cmd.app, name="client", help="Client integration helpers")

# Mount the dev umbrella group
app.add_typer(dev_group, name="dev", help="Local development and runtime")

# Mount cloud commands
app.add_typer(cloud_app, name="cloud", help="MCP Agent Cloud commands")

# Register key cloud commands directly as top-level aliases
app.command("deploy", help="Deploy an MCP agent (alias for 'cloud deploy')")(
    deploy_config
)
app.command(
    "login", help="Authenticate to MCP Agent Cloud API (alias for 'cloud login')"
)(login)


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
