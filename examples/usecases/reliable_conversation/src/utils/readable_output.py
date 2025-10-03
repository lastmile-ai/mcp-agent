"""
Readable output formatting for RCM that works with existing mcp-agent logging.
Separates user-facing output from debug logs while keeping canonical patterns.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import re


@dataclass
class OutputConfig:
    """Configuration for output formatting"""

    verbosity: str = "normal"  # minimal, normal, verbose
    show_quality_bars: bool = True
    use_color: bool = True
    max_response_preview: int = (
        3000  # Very generous - we want to read the conversation!
    )
    show_timing_info: bool = False

    def __post_init__(self):
        if self.verbosity not in ["minimal", "normal", "verbose"]:
            raise ValueError(f"Invalid verbosity: {self.verbosity}")


class ReadableFormatter:
    """Formats RCM output for human readability while preserving logging"""

    def __init__(
        self, console: Optional[Console] = None, config: Optional[OutputConfig] = None
    ):
        self.console = console or Console()
        self.config = config or OutputConfig()

    def format_quality_score(self, score: float, issues: List[str] = None) -> str:
        """Format quality score with visual indicator"""
        if not self.config.show_quality_bars:
            return f"Quality: {score:.0%}"

        # Create visual bar
        bar_width = 20
        filled = int(score * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Color based on score
        if score >= 0.8:
            color = "green"
            icon = "✓"
        elif score >= 0.6:
            color = "yellow"
            icon = "⚠"
        else:
            color = "red"
            icon = "✗"

        if not self.config.use_color:
            return f"{icon} Quality: {score:.0%}"

        result = (
            f"Quality: [{color}]{bar}[/{color}] [{color}]{score:.0%} {icon}[/{color}]"
        )

        # Add issues if present and not minimal verbosity
        if issues and self.config.verbosity != "minimal":
            for issue in issues[:2]:  # Limit to first 2 issues
                result += f"\n  [yellow]⚠ {issue}[/yellow]"

        return result

    def format_conversation_turn(
        self,
        user_input: str,
        response: str,
        quality_metrics: Optional[Dict[str, Any]] = None,
        turn_number: int = 1,
    ) -> None:
        """Display a conversation turn with formatting"""

        # Show turn header if verbose
        if self.config.verbosity == "verbose":
            self.console.print(f"\n[dim]─── Turn {turn_number} ───[/dim]")

        # User input panel - don't truncate user input, just wrap it
        self.console.print(
            Panel(
                user_input,
                title="[bold blue]You[/bold blue]",
                border_style="blue",
                padding=(0, 1),
            )
        )

        # Assistant response panel
        # Check if response contains code
        if self._contains_code(response):
            formatted_response = self._format_code_response(response)
        else:
            # Don't truncate - we want to read the full conversation!
            formatted_response = response

        self.console.print(
            Panel(
                formatted_response,
                title="[bold green]Assistant[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )

        # Quality metrics if available
        if quality_metrics and self.config.verbosity != "minimal":
            overall_score = quality_metrics.get("overall_score", 0)
            issues = quality_metrics.get("issues", [])

            quality_display = self.format_quality_score(overall_score, issues)
            self.console.print(f"[dim]{quality_display}[/dim]")

    def _contains_code(self, text: str) -> bool:
        """Check if text contains code blocks"""
        return "```" in text or bool(
            re.search(r"\b(def|class|import|function|var|let|const)\b", text)
        )

    def _format_code_response(self, response: str) -> str:
        """Format response containing code with syntax highlighting"""
        # For now, return as-is - Rich will handle basic formatting
        # Could enhance with syntax highlighting if needed
        return response

    def format_requirements_status(self, requirements: List[Dict[str, Any]]) -> None:
        """Display requirements tracking status"""
        if not requirements:
            self.console.print("[dim]No requirements tracked yet[/dim]")
            return

        table = Table(title="Requirements Status", show_header=True)
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Description", style="white")
        table.add_column("Status", justify="center", width=10)
        table.add_column("Turn", justify="center", width=6)

        for req in requirements:
            status = req.get("status", "pending")
            if status == "pending":
                status_display = "[yellow]○ Pending[/yellow]"
            elif status == "addressed":
                status_display = "[green]✓ Done[/green]"
            else:
                status_display = "[blue]◐ Partial[/blue]"

            # Truncate long descriptions
            desc = req.get("description", "")
            if len(desc) > 50:
                desc = desc[:47] + "..."

            table.add_row(
                req.get("id", "")[:8],
                desc,
                status_display,
                str(req.get("source_turn", "")),
            )

        self.console.print(table)

    def format_conversation_stats(self, stats: Dict[str, Any]) -> None:
        """Display conversation statistics"""
        table = Table(title="Conversation Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in stats.items():
            # Format the key nicely
            display_key = key.replace("_", " ").title()

            # Format the value
            if isinstance(value, float):
                display_value = f"{value:.2f}"
            elif isinstance(value, list):
                display_value = str(len(value))
            else:
                display_value = str(value)

            table.add_row(display_key, display_value)

        self.console.print(table)

    def show_welcome(self, app_name: str = "Reliable Conversation Manager") -> None:
        """Show welcome message"""
        self.console.print(
            Panel.fit(
                f"[bold blue]{app_name}[/bold blue]\n\n"
                "Multi-turn chat with quality control based on 'LLMs Get Lost' research\n\n"
                "Commands: [dim]/stats, /requirements, /exit[/dim]",
                border_style="blue",
            )
        )

    def show_thinking(self, message: str = "Processing...") -> None:
        """Show thinking indicator"""
        if self.config.verbosity != "minimal":
            self.console.print(f"[dim]🤔 {message}[/dim]")

    def show_progress(self, message: str, elapsed_time: float = 0) -> None:
        """Show progress update with optional elapsed time"""
        if elapsed_time > 0:
            self.console.print(f"[dim]🔄 {message} ({elapsed_time:.0f}s)[/dim]")
        else:
            self.console.print(f"[dim]🔄 {message}[/dim]")

    def show_error(self, error: str) -> None:
        """Show error message"""
        self.console.print(f"[red]❌ Error: {error}[/red]")

    def show_warning(self, warning: str) -> None:
        """Show warning message"""
        self.console.print(f"[yellow]⚠️  {warning}[/yellow]")

    def show_success(self, message: str) -> None:
        """Show success message"""
        self.console.print(f"[green]✅ {message}[/green]")


def safe_format(content, formatter_func):
    """Graceful degradation when Rich formatting fails"""
    try:
        return formatter_func(content)
    except Exception:
        # Fallback to plain text
        return str(content)
