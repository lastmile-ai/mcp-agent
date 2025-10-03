#!/usr/bin/env python3
"""MCP Event Viewer"""

import json
import sys
import tty
import termios
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

from mcp_agent.logging.event_progress import convert_log_event, ProgressEvent
from mcp_agent.logging.events import Event


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

    def __init__(self, events: List[Event]):
        self.events = events
        self.total = len(events)
        self.current = 0
        self.current_iteration: Optional[int] = None
        self.tool_calls = 0
        self.progress_events: List[ProgressEvent] = []
        self._process_current()

    def next(self, steps: int = 1) -> None:
        """Move forward n steps."""
        for _ in range(steps):
            if self.current < self.total - 1:
                self.current += 1
                self._process_current()

    def prev(self, steps: int = 1) -> None:
        """Move backward n steps."""
        if self.current > 0:
            self.current = max(0, self.current - steps)
            # Need to rebuild progress events up to this point
            self._rebuild_progress_events()

    def _rebuild_progress_events(self) -> None:
        """Rebuild progress events up to current position."""
        self.progress_events = []
        for i in range(self.current + 1):
            progress_event = convert_log_event(self.events[i])
            if progress_event:
                if not self.progress_events or str(progress_event) != str(
                    self.progress_events[-1]
                ):
                    self.progress_events.append(progress_event)

    def _process_current(self) -> None:
        """Process the current event."""
        event = self.events[self.current]
        message = event.message

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

        # Update progress events
        progress_event = convert_log_event(event)
        if progress_event:
            if not self.progress_events or str(progress_event) != str(
                self.progress_events[-1]
            ):
                self.progress_events.append(progress_event)

    def render(self) -> Panel:
        """Render current event state."""
        # Create the main layout
        main_layout = Layout()

        # State section
        state_text = Text()
        state_text.append("Current Status:\n", style="bold")
        state_text.append("Iteration: ", style="bold")
        state_text.append(f"{self.current_iteration or 'None'}\n", style="blue")
        state_text.append(f"Event: {self.current + 1}/{self.total}\n", style="cyan")
        state_text.append(f"Tool Calls: {self.tool_calls}\n", style="magenta")

        # Current event details
        if self.events:
            event = self.events[self.current]
            event_str = f"[{event.type}] {event.namespace}: {event.message}"
            # Get console width and account for panel borders/padding
            max_width = Console().width - 4
            if len(event_str) > max_width:
                event_str = event_str[: max_width - 3] + "..."
            state_text.append(event_str + "\n", style="yellow")

        # Progress event section
        if self.progress_events:
            latest_event = self.progress_events[-1]
            progress_text = Text("\nLatest Progress Event:\n", style="bold")
            progress_text.append("Action: ", style="bold")
            progress_text.append(f"{latest_event.action}\n", style="cyan")
            progress_text.append("Target: ", style="bold")
            progress_text.append(f"{latest_event.target}\n", style="green")
            # Add agent name from event data
            try:
                current_event = self.events[self.current]
                agent = current_event.data.get("data", {}).get("agent_name", "")
                if not agent:  # Fallback to namespace if agent_name not found
                    agent = (
                        current_event.namespace.split(".")[-1]
                        if current_event.namespace
                        else ""
                    )
                if agent:
                    progress_text.append("Agent: ", style="bold")
                    progress_text.append(f"{agent}\n", style="yellow")
            except (AttributeError, KeyError):
                pass  # Skip agent display if data is malformed

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
            Layout(Panel(controls_text, title="Controls"), size=5),
        )

        return Panel(main_layout, title="MCP Event Viewer")


def load_events(path: Path) -> List[Event]:
    """Load events from JSONL file."""
    events = []
    print(f"Loading events from {path}")  # Debug
    try:
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        raw_event = json.loads(line)
                        # Convert from log format to event format
                        event = Event(
                            type=raw_event.get("level", "info").lower(),
                            namespace=raw_event.get("namespace", ""),
                            message=raw_event.get("message", ""),
                            timestamp=datetime.fromisoformat(raw_event["timestamp"]),
                            data=raw_event.get("data", {}),
                        )
                        events.append(event)
                    except Exception as e:
                        print(f"Error on line {line_num}: {e}")
                        print(f"Line content: {line.strip()}")
                        raise
    except Exception as e:
        print(f"Error loading file: {e}")
        raise

    print(f"Loaded {len(events)} events")  # Debug
    return events


def main(log_file: str):
    """View MCP Agent events from a log file."""
    events = load_events(Path(log_file))
    if not events:
        print("No events loaded!")
        return

    display = EventDisplay(events)
    console = Console()

    # Main display loop
    while True:
        # Clear screen and show current state
        # TODO turn this in to a live display
        console.clear()
        console.print(display.render())

        # Get input
        try:
            key = get_key()

            if key == "l":  # Next one step
                display.next()
            elif key == "L":  # Next ten steps
                display.next(10)
            elif key == "h":  # Previous one step
                display.prev()
            elif key == "H":  # Previous ten steps
                display.prev(10)
            elif key in {"q", "Q"}:  # Quit
                break
        except Exception as e:
            print(f"\nError handling input: {e}")
            break


if __name__ == "__main__":
    typer.run(main)
