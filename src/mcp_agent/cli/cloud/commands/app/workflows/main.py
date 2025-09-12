from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.cloud.commands.workflows.utils import (
    print_workflows,
    print_workflow_runs,
)
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
)
from mcp_agent.cli.core.utils import run_async
from ...utils import resolve_server
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPAppClient
from mcp_agent.cli.mcp_app.mcp_client import (
    MCPClientSession,
    WorkflowRun,
    mcp_connection_session,
)
from mcp_agent.cli.utils.ux import (
    console,
    print_error,
)


def list_app_workflows(
    app_id_or_url: str = typer.Option(
        None,
        "--id",
        "-i",
        help="ID or server URL of the app or app configuration to list workflows from.",
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
        envvar=ENV_API_BASE_URL,
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
        envvar=ENV_API_KEY,
    ),
) -> None:
    """List workflow details (available workflows and recent workflow runs) for an MCP App."""
    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()

    if not effective_api_key:
        raise CLIError(
            "Must be logged in list workflow details. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option."
        )

    client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    if not app_id_or_url:
        raise CLIError(
            "You must provide an app ID or server URL to view its workflows."
        )

    try:
        app_or_config = resolve_server(client, app_id_or_url)

        if not app_or_config:
            raise CLIError(f"App or config with ID or URL '{app_id_or_url}' not found.")

        if not app_or_config.appServerInfo:
            raise CLIError(
                f"App or config with ID or URL '{app_id_or_url}' has no server info available."
            )

        server_url = app_or_config.appServerInfo.serverUrl
        if not server_url:
            raise CLIError("No server URL available for this app.")

        run_async(
            print_mcp_server_workflow_details(
                server_url=server_url, api_key=effective_api_key
            )
        )

    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key."
        ) from e
    except Exception as e:
        raise CLIError(
            f"Error listing workflow details for app or config with ID or URL {app_id_or_url}: {str(e)}"
        ) from e


async def print_mcp_server_workflow_details(server_url: str, api_key: str) -> None:
    """Prints the MCP server workflow details."""
    try:
        async with mcp_connection_session(server_url, api_key) as mcp_client_session:
            choices = {
                "1": "List Workflows",
                "2": "List Workflow Runs",
                "0": "List All",
            }

            # Print the numbered options
            console.print("\n[bold]What would you like to display?[/bold]")
            for key, description in choices.items():
                console.print(f"[cyan]{key}[/cyan]: {description}")

            try:
                choice = Prompt.ask(
                    "\nWhat would you like to display?",
                    choices=list(choices.keys()),
                    default="0",
                    show_choices=False,
                )

                if choice in ["0", "1"]:
                    await print_workflows_list(mcp_client_session)
                if choice in ["0", "2"]:
                    await print_runs_list(mcp_client_session)
            except (EOFError, KeyboardInterrupt):
                return

    except Exception as e:
        raise CLIError(
            f"Error getting workflow details from MCP server at {server_url}: {str(e)}"
        ) from e


async def print_workflows_list(session: MCPClientSession) -> None:
    """Prints the available workflow types for the server."""
    try:
        with console.status("[bold green]Fetching server workflows...", spinner="dots"):
            res = await session.list_workflows()

        print_workflows(res.workflows if res and res.workflows else [])

    except Exception as e:
        print_error(f"Error fetching workflows: {str(e)}")


async def print_runs_list(session: MCPClientSession) -> None:
    """Prints the latest workflow runs on the server."""
    try:
        with console.status("[bold green]Fetching workflow runs...", spinner="dots"):
            res = await session.list_workflow_runs()

        if not res.workflow_runs:
            console.print(
                Panel(
                    "[yellow]No workflow runs found[/yellow]",
                    title="Workflow Runs",
                    border_style="blue",
                )
            )
            return

        def get_start_time(run: WorkflowRun):
            try:
                return (
                    run.temporal.start_time
                    if run.temporal and run.temporal.start_time is not None
                    else 0
                )
            except AttributeError:
                return 0

        sorted_runs = sorted(
            res.workflow_runs,
            key=get_start_time,
            reverse=True,
        )

        print_workflow_runs(sorted_runs)

    except Exception as e:
        print_error(f"Error fetching workflow runs: {str(e)}")
