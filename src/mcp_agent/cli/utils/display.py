"""
Display utilities for CLI output formatting.
"""

from typing import List, Any, Optional, Dict
from rich.console import Console
from rich.table import Table


console = Console()


class ParallelResultsDisplay:
    """Display parallel execution results in a clean, organized format."""

    def __init__(self):
        self.console = console

    def show_results(self, results: List[tuple[str, str]]) -> None:
        """
        Display parallel agent results with model names and outputs.

        Args:
            results: List of (model_name, output) tuples
        """
        if not results:
            return

        # Display header
        self.console.print()
        self.console.print("[dim]Parallel execution complete[/dim]")
        self.console.print()

        # Display results for each model
        for i, (model_name, output) in enumerate(results):
            if i > 0:
                # Simple full-width separator
                self.console.print()
                self.console.print("─" * self.console.size.width, style="dim")
                self.console.print()

            # Model header with green indicator
            self.console.print(
                f"[green]▎[/green] [bold green]{model_name}[/bold green]"
            )
            self.console.print()

            # Display content
            if output.startswith("ERROR:"):
                self.console.print(output, style="red")
            else:
                self.console.print(output)

        # Summary footer
        self.console.print()
        self.console.print("─" * self.console.size.width, style="dim")
        self.console.print(f"[dim]{len(results)} models completed[/dim]")
        self.console.print()


class TokenUsageDisplay:
    """Display token usage information in a formatted way."""

    def __init__(self):
        self.console = console

    def show_summary(self, summary: Dict[str, Any]) -> None:
        """Display token usage summary."""
        table = Table(
            title="Token Usage Summary", show_header=True, header_style="bold cyan"
        )
        table.add_column("Model", style="cyan", no_wrap=True)
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        table.add_column("Total Tokens", justify="right")
        table.add_column("Cost", justify="right")

        # If summary has model breakdowns
        if "models" in summary:
            for model_name, stats in summary["models"].items():
                table.add_row(
                    model_name,
                    str(stats.get("input_tokens", 0)),
                    str(stats.get("output_tokens", 0)),
                    str(stats.get("total_tokens", 0)),
                    f"${stats.get('cost', 0):.4f}" if "cost" in stats else "-",
                )
        else:
            # Single row summary
            table.add_row(
                "Total",
                str(summary.get("cumulative_input_tokens", 0)),
                str(summary.get("cumulative_output_tokens", 0)),
                str(summary.get("cumulative_total_tokens", 0)),
                f"${summary.get('cumulative_cost', 0):.4f}"
                if "cumulative_cost" in summary
                else "-",
            )

        self.console.print(table)


def format_tool_list(tools: List[Any], server_name: Optional[str] = None) -> None:
    """Format and display a list of tools."""
    if not tools:
        console.print("[yellow]No tools found[/yellow]")
        return

    table = Table(
        title=f"Tools{f' from {server_name}' if server_name else ''}", show_header=True
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    for tool in tools:
        name = getattr(tool, "name", str(tool))
        desc = getattr(tool, "description", "")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        table.add_row(name, desc)

    console.print(table)


def format_resource_list(
    resources: List[Any], server_name: Optional[str] = None
) -> None:
    """Format and display a list of resources."""
    if not resources:
        console.print("[yellow]No resources found[/yellow]")
        return

    table = Table(
        title=f"Resources{f' from {server_name}' if server_name else ''}",
        show_header=True,
    )
    table.add_column("URI", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Description", style="dim")

    for resource in resources:
        uri = str(getattr(resource, "uri", ""))
        name = getattr(resource, "name", "")
        desc = getattr(resource, "description", "")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        table.add_row(uri, name, desc)

    console.print(table)


def format_server_list(servers: List[str]) -> None:
    """Format and display a list of servers."""
    if not servers:
        console.print("[yellow]No servers configured[/yellow]")
        return

    table = Table(title="Available Servers", show_header=False, box=None)
    table.add_column("Server", style="cyan")

    for server in servers:
        table.add_row(server)

    console.print(table)


def show_progress(message: str) -> None:
    """Show a progress message."""
    console.print(f"[dim cyan]▸ {message}[/dim cyan]")


def show_error(message: str) -> None:
    """Show an error message."""
    console.print(f"[red]✗ {message}[/red]")


def show_success(message: str) -> None:
    """Show a success message."""
    console.print(f"[green]✓ {message}[/green]")


def show_warning(message: str) -> None:
    """Show a warning message."""
    console.print(f"[yellow]⚠ {message}[/yellow]")
