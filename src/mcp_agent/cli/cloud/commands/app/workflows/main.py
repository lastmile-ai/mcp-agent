import json
import textwrap
from typing import Optional
from datetime import datetime

import typer
from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from mcp_agent.cli.auth import load_api_key_credentials
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
            f"Error connecting to MCP server at {server_url}: {str(e)}"
        ) from e


# FastTool includes 'self' in the run parameters schema, so remove it for clarity
def clean_run_parameters(schema: dict) -> dict:
    schema = schema.copy()

    if "properties" in schema and "self" in schema["properties"]:
        schema["properties"].pop("self")

    if "required" in schema and "self" in schema["required"]:
        schema["required"] = [r for r in schema["required"] if r != "self"]

    return schema


async def print_workflows_list(session: MCPClientSession) -> None:
    """Prints the available workflow types for the server."""
    try:
        with console.status("[bold green]Fetching server workflows...", spinner="dots"):
            res = await session.list_workflows()

        if not res.workflows:
            console.print(
                Panel(
                    "[yellow]No workflows found[/yellow]",
                    title="Workflows",
                    border_style="blue",
                )
            )
            return

        panels = []

        for workflow in res.workflows:
            header = Text(workflow.name, style="bold cyan")
            desc = textwrap.dedent(
                workflow.description or "No description available"
            ).strip()
            body_parts: list = [Text(desc, style="white")]

            # Capabilities
            capabilities = getattr(workflow, "capabilities", [])
            cap_text = Text("\nCapabilities:\n", style="bold green")
            cap_text.append_text(Text(", ".join(capabilities) or "None", style="white"))
            body_parts.append(cap_text)

            # Tool Endpoints
            tool_endpoints = getattr(workflow, "tool_endpoints", [])
            endpoints_text = Text("\nTool Endpoints:\n", style="bold green")
            endpoints_text.append_text(
                Text("\n".join(tool_endpoints) or "None", style="white")
            )
            body_parts.append(endpoints_text)

            # Run Parameters
            if workflow.run_parameters:
                run_params = clean_run_parameters(workflow.run_parameters)
                properties = run_params.get("properties", {})
                if len(properties) > 0:
                    schema_str = json.dumps(run_params, indent=2)
                    schema_syntax = Syntax(
                        schema_str, "json", theme="monokai", word_wrap=True
                    )
                    body_parts.append(Text("\nRun Parameters:", style="bold magenta"))
                    body_parts.append(schema_syntax)

            body = Group(*body_parts)

            panels.append(
                Panel(
                    body,
                    title=header,
                    border_style="green",
                    expand=False,
                )
            )

        console.print(Panel(Group(*panels), title="Workflows", border_style="blue"))

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
                return run.temporal.start_time if run.temporal else 0
            except AttributeError:
                return 0

        sorted_runs = sorted(
            res.workflow_runs,
            key=get_start_time,
            reverse=True,
        )

        console.print(f"\n[bold blue] Workflow Runs ({len(sorted_runs)})[/bold blue]")

        for i, run in enumerate(sorted_runs):
            if i > 0:
                console.print()

            start = getattr(run.temporal, "start_time", None)
            start_str = (
                datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S")
                if start
                else "N/A"
            )

            end = getattr(run.temporal, "close_time", None)
            end_str = (
                datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M:%S")
                if end
                else "N/A"
            )

            status = run.status.lower()
            if status == "completed":
                status_text = f"[green]🟢 {status}[/green]"
            elif status == "error" or status == "failed":
                status_text = f"[red]🔴 {status}[/red]"
            elif status == "running":
                status_text = f"[yellow]🔄 {status}[/yellow]"
            else:
                status_text = f"❓ {status}"

            console.print(
                f"[bold cyan]{run.name or 'Unnamed Workflow'}[/bold cyan] {status_text}"
            )
            console.print(f"  Run ID: {run.id}")

            if run.temporal and run.temporal.workflow_id:
                console.print(f"  Workflow ID: {run.temporal.workflow_id}")

            console.print(f"  Started: {start_str}")
            if end_str != "N/A":
                console.print(f"  Completed: {end_str}")

            # Show execution time if available
            if hasattr(run.temporal, "execution_time") and run.temporal.execution_time:
                duration = end - start if (start and end) else None
                if duration:
                    console.print(f"  Duration: {duration:.2f}s")

    except Exception as e:
        print_error(f"Error fetching workflow runs: {str(e)}")
