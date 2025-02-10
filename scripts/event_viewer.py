#!/usr/bin/env python3
"""MCP Event Viewer"""

import json
import sys
import tty
import termios
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

from mcp_agent.event_progress import convert_log_event, ProgressEvent


def get_key() -> str:
    """Get a single keypress."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class EventDisplay:
    """Display MCP events from a log file."""

    def __init__(self, events: list):
        self.events = events
        self.total = len(events)
        self.current = 0
        self.current_iteration: Optional[int] = None
        self.tool_calls = 0
        self.progress_events: List[ProgressEvent] = []

    def next(self) -> None:
        """Move to next event."""
        if self.current < self.total:
            event = self.events[self.current]
            self._process_event(event)

            # Convert to progress event if applicable
            progress_event = convert_log_event(event)
            if progress_event:
                if not self.progress_events or str(progress_event) != str(
                    self.progress_events[-1]
                ):
                    self.progress_events.append(progress_event)

            self.current += 1

    def prev(self) -> None:
        """Move to previous event."""
        if self.current > 0:
            # Reset state and replay up to previous event
            self._reset_state()
            for i in range(self.current - 1):
                self._process_event(self.events[i])

                # Rebuild progress events
                progress_event = convert_log_event(self.events[i])
                if progress_event:
                    if not self.progress_events or str(progress_event) != str(
                        self.progress_events[-1]
                    ):
                        self.progress_events.append(progress_event)

            self.current -= 1

    def _reset_state(self) -> None:
        """Reset state for replay."""
        self.current_iteration = None
        self.tool_calls = 0
        self.progress_events = []

    def _process_event(self, event: dict) -> None:
        """Update state based on event."""
        message = event.get("message", "")

        # Track iterations
        if "Iteration" in message:
            try:
                self.current_iteration = int(
                    message.split("Iteration")[1].split(":")[0]
                )
            except (ValueError, IndexError):
                pass

        # Track tool calls
        if "Tool call" in message or "Calling tool" in message:
            self.tool_calls += 1

    def render(self) -> Panel:
        """Render current event state."""

        # Create the main layout
        main_layout = Layout()

        # State section
        state_text = Text()
        state_text.append("Current Status:\n", style="bold")
        state_text.append("Iteration: ", style="bold")
        state_text.append(f"{self.current_iteration or 'None'}\n", style="blue")
        state_text.append(f"Event: {self.current}/{self.total}\n", style="cyan")
        state_text.append(f"Tool Calls: {self.tool_calls}\n", style="magenta")
        # Add current event JSON line if we have events
        if self.events and self.current < len(self.events):
            current_event = json.dumps(self.events[self.current])
            # Get console width and account for panel borders/padding (approximately 4 chars)
            max_width = Console().width - 4
            if len(current_event) > max_width:
                current_event = current_event[: max_width - 3] + "..."
            state_text.append(current_event + "\n", style="yellow")

        # Progress event section
        if self.progress_events:
            latest_event = self.progress_events[-1]
            progress_text = Text("\nLatest Progress Event:\n", style="bold")
            progress_text.append("Action: ", style="bold")
            progress_text.append(f"{latest_event.action}\n", style="cyan")
            progress_text.append("Target: ", style="bold")
            progress_text.append(f"{latest_event.target}\n", style="green")
            if latest_event.details:
                progress_text.append("Details: ", style="bold")
                progress_text.append(f"{latest_event.details}\n", style="magenta")
        else:
            progress_text = Text("\nNo progress events yet\n", style="dim")

        # Controls
        controls_text = Text(
            "\n[h] prev • [l] next • [H] prev x10 • [L] next x10 • [q] quit",
            style="dim",
        )

        # Combine sections into layout
        main_layout.split(
            Layout(Panel(state_text, title="Status"), size=8),
            Layout(Panel(progress_text, title="Progress"), size=8),
            Layout(Panel(controls_text, title="Controls"), size=6),
        )

        return Panel(main_layout, title="MCP Event Viewer")


def load_events(path: Path) -> list:
    """Load events from JSONL file."""
    events = []
    with open(path) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def main(log_file: str):
    """View MCP Agent events from a log file."""
    events = load_events(Path(log_file))
    display = EventDisplay(events)
    console = Console()

    with Live(
        display.render(),
        console=console,
        screen=True,
        transient=True,
        auto_refresh=False,  # Only refresh on demand
    ) as live:
        while True:
            key = get_key()

            if key == "l":  # Next one step
                display.next()
            elif key == "L":  # Next ten steps
                for _ in range(10):
                    display.next()
            elif key == "h":  # Previous one step
                display.prev()
            elif key == "H":  # Previous ten steps
                for _ in range(10):
                    display.prev()
            elif key in {"q", "Q"}:  # Quit
                break

            live.update(display.render())
            live.refresh()


if __name__ == "__main__":
    typer.run(main)
