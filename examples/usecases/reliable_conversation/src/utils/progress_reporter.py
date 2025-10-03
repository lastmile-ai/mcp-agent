"""
Progress reporter for showing internal workflow steps during test execution.
"""

from rich.console import Console
from typing import Optional
import time


class ProgressReporter:
    """Reports workflow progress to console during testing"""

    def __init__(self, console: Optional[Console] = None, enabled: bool = True):
        self.console = console or Console()
        self.enabled = enabled
        self.start_time = time.time()

    def step(self, message: str, details: str = ""):
        """Report a workflow step"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time

        if details:
            self.console.print(f"[dim]🔄 {message}: {details} ({elapsed:.1f}s)[/dim]")
        else:
            self.console.print(f"[dim]🔄 {message} ({elapsed:.1f}s)[/dim]")

    def thinking(self, message: str = "Processing"):
        """Report thinking/processing"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time
        self.console.print(f"[dim]🤔 {message}... ({elapsed:.1f}s)[/dim]")

    def quality_check(self, score: float, issues: int = 0):
        """Report quality evaluation results"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time
        if issues > 0:
            self.console.print(
                f"[dim]✨ Quality evaluated: {score:.0%} ({issues} issues found) ({elapsed:.1f}s)[/dim]"
            )
        else:
            self.console.print(
                f"[dim]✨ Quality evaluated: {score:.0%} (no issues) ({elapsed:.1f}s)[/dim]"
            )

    def requirement_extraction(self, count: int):
        """Report requirement extraction"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time
        self.console.print(
            f"[dim]📋 Requirements extracted: {count} found ({elapsed:.1f}s)[/dim]"
        )

    def context_consolidation(self, from_chars: int, to_chars: int):
        """Report context consolidation"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time
        self.console.print(
            f"[dim]📚 Context consolidated: {from_chars} → {to_chars} chars ({elapsed:.1f}s)[/dim]"
        )

    def show_llm_interaction(
        self, role: str, prompt: str, response: str, truncate_at: int = 500
    ):
        """Show LLM interaction details"""
        if not self.enabled:
            return

        elapsed = time.time() - self.start_time

        # Truncate long prompts/responses for readability
        if len(prompt) > truncate_at:
            truncated_prompt = (
                prompt[:truncate_at]
                + f"\n[dim]... (truncated, {len(prompt)} total chars)[/dim]"
            )
        else:
            truncated_prompt = prompt

        if len(response) > truncate_at:
            truncated_response = (
                response[:truncate_at]
                + f"\n[dim]... (truncated, {len(response)} total chars)[/dim]"
            )
        else:
            truncated_response = response

        self.console.print(f"\n[dim]🤖 {role} LLM Interaction ({elapsed:.1f}s):[/dim]")
        self.console.print("[dim]┌─ Prompt:[/dim]")
        self.console.print(f"[dim]{truncated_prompt}[/dim]")
        self.console.print("[dim]└─ Response:[/dim]")
        self.console.print(f"[dim]{truncated_response}[/dim]")
        self.console.print()  # Add spacing


# Global instance for easy access
_global_reporter: Optional[ProgressReporter] = None


def get_progress_reporter() -> Optional[ProgressReporter]:
    """Get the current progress reporter"""
    return _global_reporter


def set_progress_reporter(reporter: Optional[ProgressReporter]):
    """Set the global progress reporter"""
    global _global_reporter
    _global_reporter = reporter


def report_step(message: str, details: str = ""):
    """Report a step using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.step(message, details)


def report_thinking(message: str = "Processing"):
    """Report thinking using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.thinking(message)


def report_quality_check(score: float, issues: int = 0):
    """Report quality check using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.quality_check(score, issues)


def report_requirement_extraction(count: int):
    """Report requirement extraction using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.requirement_extraction(count)


def report_context_consolidation(from_chars: int, to_chars: int):
    """Report context consolidation using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.context_consolidation(from_chars, to_chars)


def show_llm_interaction(role: str, prompt: str, response: str, truncate_at: int = 500):
    """Show LLM interaction using the global reporter"""
    reporter = get_progress_reporter()
    if reporter:
        reporter.show_llm_interaction(role, prompt, response, truncate_at)
