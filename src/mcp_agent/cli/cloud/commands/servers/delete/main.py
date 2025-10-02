import typer
from rich.panel import Panel

from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp
from ...utils import (
    setup_authenticated_client,
    resolve_server,
    handle_server_api_errors,
    get_server_name,
    get_server_id,
)
from mcp_agent.cli.utils.ux import console, print_info


@handle_server_api_errors
def delete_server(
    id_or_url: str = typer.Argument(
        ..., help="App ID, server URL, or app name to delete"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force deletion without confirmation prompt"
    ),
) -> None:
    """Delete a specific MCP Server."""
    client = setup_authenticated_client()
    server = resolve_server(client, id_or_url)

    # Determine server type and delete function
    if isinstance(server, MCPApp):
        server_type = "Deployed Server"
        delete_function = client.delete_app
    else:
        server_type = "Configured Server"
        delete_function = client.delete_app_configuration

    server_name = get_server_name(server)
    server_id = get_server_id(server)

    if not force:
        console.print(
            Panel(
                f"Name: [cyan]{server_name}[/cyan]\n"
                f"Type: [cyan]{server_type}[/cyan]\n"
                f"ID: [cyan]{server_id}[/cyan]\n\n"
                f"[bold red]⚠️  This action cannot be undone![/bold red]",
                title="Server to Delete",
                border_style="red",
                expand=False,
            )
        )

        confirm = typer.confirm(
            f"\nAre you sure you want to delete this {server_type.lower()}?"
        )
        if not confirm:
            print_info("Deletion cancelled.")
            return

    if isinstance(server, MCPApp):
        can_delete = run_async(client.can_delete_app(server_id))
    else:
        can_delete = run_async(client.can_delete_app_configuration(server_id))

    if not can_delete:
        raise CLIError(
            f"You do not have permission to delete this {server_type.lower()}. "
            f"You can only delete servers that you created."
        )
    deleted_id = run_async(delete_function(server_id))

    console.print(
        Panel(
            f"[green]✅ Successfully deleted {server_type.lower()}[/green]\n\n"
            f"Name: [cyan]{server_name}[/cyan]\n"
            f"ID: [cyan]{deleted_id}[/cyan]",
            title="Deletion Complete",
            border_style="green",
            expand=False,
        )
    )
