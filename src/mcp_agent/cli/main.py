"""
Top-level CLI entrypoint for mcp-agent (non-cloud + cloud groups).

Uses Typer and Rich. This module wires together all non-cloud command groups
and mounts the existing cloud CLI under the `cloud` namespace. Initial
implementation provides scaffolding; individual commands can be implemented
progressively.
"""

from __future__ import annotations

import typer
from rich.console import Console

# Mount existing cloud CLI
try:
    from mcp_agent.cli.cloud.main import app as cloud_app  # type: ignore
except Exception:  # pragma: no cover - cloud is optional for non-cloud development
    cloud_app = typer.Typer(help="Cloud commands (unavailable)")


# Local command groups (scaffolded)
from mcp_agent.cli.commands import (
    init as init_cmd,
    quickstart as quickstart_cmd,
    config as config_cmd,
    keys as keys_cmd,
    models as models_cmd,
    go as go_cmd,
    check as check_cmd,
)

from mcp_agent.cli.cloud.commands import deploy_config, login, logout, whoami
from mcp_agent.cli.utils.typer_utils import HelpfulTyperGroup

app = typer.Typer(
    help="mcp-agent CLI",
    add_completion=False,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=HelpfulTyperGroup,
)


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


# Mount non-cloud command groups
app.add_typer(init_cmd.app, name="init", help="Scaffold a new mcp-agent project")
app.add_typer(quickstart_cmd.app, name="quickstart", help="Copy curated examples")
app.add_typer(go_cmd.app, name="go", help="Quick interactive agent")
app.add_typer(check_cmd.app, name="check", help="Check configuration and environment")
app.add_typer(config_cmd.app, name="config", help="Manage and inspect configuration")
app.add_typer(keys_cmd.app, name="keys", help="Manage provider API keys")
app.add_typer(models_cmd.app, name="models", help="List and manage models")

# TODO: Uncomment after testing - Local Development and beyond
# app.add_typer(chat_cmd.app, name="chat", help="Ephemeral REPL for quick iteration")
# app.add_typer(dev_cmd.app, name="dev", help="Run app locally with live reload")
# app.add_typer(
#     invoke_cmd.app, name="invoke", help="Invoke agent/workflow programmatically"
# )
# app.add_typer(serve_cmd.app, name="serve", help="Serve app as an MCP server")
# app.add_typer(server_cmd.app, name="server", help="Local server helpers")
# app.add_typer(
#     build_cmd.app, name="build", help="Preflight and bundle prep for deployment"
# )
# app.add_typer(logs_cmd.app, name="logs", help="Tail local logs")
# app.add_typer(doctor_cmd.app, name="doctor", help="Comprehensive diagnostics")
# app.add_typer(configure_cmd.app, name="configure", help="Client integration helpers")

# Mount cloud commands
app.add_typer(cloud_app, name="cloud", help="MCP Agent Cloud commands")

# Register some key cloud commands directly as top-level commands
app.command("deploy", help="Deploy an MCP agent (alias for 'cloud deploy')")(
    deploy_config
)
app.command(
    "login", help="Authenticate to MCP Agent Cloud API (alias for 'cloud login')"
)(login)
app.command(
    "whoami", help="Print current identity and org(s) (alias for 'cloud whoami')"
)(whoami)
app.command("logout", help="Clear credentials (alias for 'cloud logout')")(logout)


def run() -> None:
    """Entry for __main__."""
    app()


if __name__ == "__main__":
    run()
