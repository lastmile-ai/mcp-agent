"""
Human-readable test runner for RCM with clean output formatting.
Works with canonical mcp-agent logging patterns.
"""

from typing import Dict, Any, List, Callable, Awaitable, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import asyncio
import time
import traceback

from .readable_output import ReadableFormatter, OutputConfig


class ReadableTestRunner:
    """Test runner that provides clear, formatted output for RCM testing"""

    def __init__(
        self, console: Optional[Console] = None, config: Optional[OutputConfig] = None
    ):
        self.console = console or Console()
        self.formatter = ReadableFormatter(self.console, config)
        self.results = []
        self.start_time = time.time()

    def show_test_header(self, title: str, description: str = ""):
        """Show test suite header"""
        content = f"[bold]{title}[/bold]"
        if description:
            content += f"\n\n{description}"

        self.console.print(Panel.fit(content, border_style="blue"))

    async def run_test_scenario(
        self,
        name: str,
        description: str,
        test_func: Callable[[], Awaitable[Dict[str, Any]]],
    ):
        """Run a test scenario with readable output"""
        self.console.print(f"\n[bold blue]━━━ {name} ━━━[/bold blue]")
        if description:
            self.console.print(f"[dim]{description}[/dim]\n")

        start_time = time.time()

        try:
            # Show intermediate progress updates for long operations
            async def run_with_progress():
                # Start the actual task
                task = asyncio.create_task(test_func())

                # Show progress messages that appear above the status
                last_message_time = start_time

                while not task.done():
                    await asyncio.sleep(3)  # Check every 3 seconds
                    elapsed = time.time() - start_time

                    # Show progressive messages
                    if elapsed > 10 and (elapsed - last_message_time) > 10:
                        self.console.print(
                            f"[dim]🔄 Still processing... ({elapsed:.0f}s elapsed)[/dim]"
                        )
                        last_message_time = elapsed
                    elif elapsed > 30 and (elapsed - last_message_time) > 15:
                        self.console.print(
                            f"[dim]⏳ Complex operation in progress... ({elapsed:.0f}s elapsed)[/dim]"
                        )
                        last_message_time = elapsed
                    elif elapsed > 60 and (elapsed - last_message_time) > 20:
                        self.console.print(
                            f"[dim]⌛ This is taking longer than usual... ({elapsed:.0f}s elapsed)[/dim]"
                        )
                        last_message_time = elapsed

                return await task

            result = await run_with_progress()

            # Calculate execution time
            execution_time = time.time() - start_time

            # Display result
            self._display_test_result(result, execution_time)
            self.results.append((name, True, result, execution_time))

        except Exception as e:
            execution_time = time.time() - start_time
            error_details = {"error": str(e), "traceback": traceback.format_exc()}

            self.console.print(f"[red]✗ Test failed: {str(e)}[/red]")
            self.results.append((name, False, error_details, execution_time))

    def _display_test_result(self, result: Dict[str, Any], execution_time: float):
        """Display test results in a readable format"""

        # Show basic test info
        if result.get("turn_number"):
            self.console.print(f"[cyan]Turn {result['turn_number']}[/cyan]")

        # Show user input if present
        if result.get("user_input"):
            user_input = result["user_input"]
            # Only truncate VERY long inputs (over 200 chars)
            if len(user_input) > 200:
                user_input = user_input[:197] + "..."

            self.console.print(
                Panel(
                    user_input,
                    title="[bold]User Input[/bold]",
                    border_style="blue",
                    padding=(0, 1),
                )
            )

        # Show assistant response - NO TRUNCATION, we want to read everything!
        if result.get("response"):
            response = result["response"]

            self.console.print(
                Panel(
                    response,
                    title="[bold]Assistant Response[/bold]",
                    border_style="green",
                    padding=(0, 1),
                )
            )

        # Show quality metrics in compact form
        if result.get("quality_metrics"):
            self._display_quality_summary(result["quality_metrics"])

        # Show execution time if significant
        if execution_time > 1.0:
            self.console.print(f"[dim]Execution time: {execution_time:.1f}s[/dim]")

        # Show test-specific assertions/validations
        if result.get("test_validations"):
            self._display_test_validations(result["test_validations"])

    def _display_quality_summary(self, metrics: Dict[str, Any]):
        """Display quality metrics in test context"""
        overall_score = metrics.get("overall_score", 0)
        issues = metrics.get("issues", [])

        # Use formatter for consistent display
        quality_display = self.formatter.format_quality_score(overall_score, issues)
        self.console.print(f"[dim]{quality_display}[/dim]")

        # Highlight specific test concerns
        if metrics.get("premature_attempt"):
            self.console.print(
                "  [yellow]⚠ Test detected premature answer attempt[/yellow]"
            )

        verbosity = metrics.get("verbosity", 0)
        if verbosity > 0.7:
            self.console.print(
                f"  [yellow]⚠ High verbosity detected ({verbosity:.0%})[/yellow]"
            )

    def _display_test_validations(self, validations: List[Dict[str, Any]]):
        """Display test-specific validations"""
        for validation in validations:
            name = validation.get("name", "Validation")
            passed = validation.get("passed", False)
            details = validation.get("details", "")

            if passed:
                self.console.print(f"  [green]✓ {name}[/green]")
            else:
                self.console.print(f"  [red]✗ {name}[/red]")
                if details:
                    self.console.print(f"    [dim]{details}[/dim]")

    def display_summary(self):
        """Display final test summary"""
        total_time = time.time() - self.start_time

        self.console.print("\n[bold blue]━━━ Test Summary ━━━[/bold blue]\n")

        # Results table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Test Scenario", style="white")
        table.add_column("Result", justify="center")
        table.add_column("Time", justify="right", style="dim")

        passed = 0
        total_execution_time = 0

        for name, success, result, execution_time in self.results:
            status = "[green]✓ PASSED[/green]" if success else "[red]✗ FAILED[/red]"
            time_display = f"{execution_time:.1f}s" if execution_time > 0.1 else "<0.1s"

            table.add_row(name, status, time_display)

            if success:
                passed += 1
            total_execution_time += execution_time

        self.console.print(table)

        # Summary stats
        total = len(self.results)
        pass_rate = (passed / total * 100) if total > 0 else 0

        summary_text = (
            f"[bold]Results:[/bold] {passed}/{total} tests passed ({pass_rate:.0f}%)\n"
            f"[bold]Total time:[/bold] {total_time:.1f}s (execution: {total_execution_time:.1f}s)"
        )

        if pass_rate == 100:
            border_style = "green"
        elif pass_rate >= 50:
            border_style = "yellow"
        else:
            border_style = "red"

        self.console.print(
            Panel(summary_text, title="Summary", border_style=border_style)
        )

        return pass_rate == 100  # Return success status

    def display_conversation_analysis(self, conversation_data: Dict[str, Any]):
        """Display analysis of conversation quality over multiple turns"""
        self.console.print("\n[bold blue]━━━ Conversation Analysis ━━━[/bold blue]\n")

        # Quality trend
        quality_history = conversation_data.get("quality_history", [])
        if quality_history:
            self._display_quality_trend(quality_history)

        # Answer bloat analysis
        answer_lengths = conversation_data.get("answer_lengths", [])
        if len(answer_lengths) > 1:
            self._display_bloat_analysis(answer_lengths)

        # Requirements tracking
        requirements = conversation_data.get("requirements", [])
        if requirements:
            self.formatter.format_requirements_status(requirements)

    def _display_quality_trend(self, quality_history: List[Dict[str, Any]]):
        """Display quality trend over conversation"""
        self.console.print("[bold]Quality Trend:[/bold]")

        # Extract scores
        scores = [q.get("overall_score", 0) for q in quality_history]

        # Simple text-based trend display
        trend_line = ""
        for i, score in enumerate(scores):
            if score >= 0.8:
                trend_line += "█"
            elif score >= 0.6:
                trend_line += "▆"
            elif score >= 0.4:
                trend_line += "▄"
            elif score >= 0.2:
                trend_line += "▂"
            else:
                trend_line += "░"

            trend_line += " "

        self.console.print(f"  {trend_line}")
        self.console.print(f"  {'  '.join(str(i + 1) for i in range(len(scores)))}")
        self.console.print("  Turn numbers\n")

    def _display_bloat_analysis(self, answer_lengths: List[int]):
        """Display answer bloat analysis"""
        bloat_ratio = (
            answer_lengths[-1] / answer_lengths[0] if answer_lengths[0] > 0 else 1.0
        )

        if bloat_ratio > 2.0:
            bloat_color = "red"
            bloat_icon = "🔴"
        elif bloat_ratio > 1.5:
            bloat_color = "yellow"
            bloat_icon = "🟡"
        else:
            bloat_color = "green"
            bloat_icon = "🟢"

        self.console.print(
            f"[bold]Answer Bloat:[/bold] [{bloat_color}]{bloat_ratio:.1f}x {bloat_icon}[/{bloat_color}]"
        )

        # Show progression
        lengths_display = " → ".join(str(length) for length in answer_lengths)
        self.console.print(f"[dim]Length progression: {lengths_display} chars[/dim]\n")


def create_test_runner(verbosity: str = "normal") -> ReadableTestRunner:
    """Create a test runner with specified verbosity"""
    config = OutputConfig(verbosity=verbosity)
    return ReadableTestRunner(config=config)
