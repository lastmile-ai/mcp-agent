#!/usr/bin/env python3
"""MCP Event Summary"""

import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from mcp_agent.logging.event_progress import convert_log_event, ProgressAction
from mcp_agent.logging.events import Event


def load_events(path: Path) -> list[Event]:
    """Load events from JSONL file."""
    events = []
    with open(path) as f:
        for line in f:
            if line.strip():
                raw_event = json.loads(line)
                # Convert from log format to event format
                event = Event(
                    type=raw_event.get("level", "info").lower(),
                    namespace=raw_event.get("namespace", ""),
                    message=raw_event.get("message", ""),
                    timestamp=datetime.fromisoformat(raw_event["timestamp"]),
                    data=raw_event.get("data", {}),  # Get data directly
                )
                events.append(event)
    return events


def create_event_table(events: list[Event]) -> Table:
    """Create a rich table for displaying events."""

    # Convert events to progress events
    progress_events = []
    for event in events:
        progress_event = convert_log_event(event)
        if progress_event:
            if not progress_events or str(progress_event) != str(progress_events[-1]):
                # Store tuple of (progress_event, original_event)
                progress_events.append((progress_event, event))

    # Create table
    table = Table(show_header=True, header_style="bold", show_lines=True)
    table.add_column("Agent", style="yellow", width=20)
    table.add_column("Action", style="cyan", width=12)
    table.add_column("Target", style="green", width=30)
    table.add_column("Details", style="magenta", width=30)

    # Add events
    for progress_event, orig_event in progress_events:
        # Extract agent name from data or fallback to namespace
        try:
            agent = orig_event.data.get("data", {}).get("agent_name", "")
            if not agent:  # Fallback to namespace if agent_name not found
                agent = (
                    orig_event.namespace.split(".")[-1] if orig_event.namespace else ""
                )
        except (AttributeError, KeyError):
            # Fallback to namespace if there's any error accessing data
            agent = orig_event.namespace.split(".")[-1] if orig_event.namespace else ""
        table.add_row(
            agent,
            progress_event.action.value,
            progress_event.target,
            progress_event.details or "",
        )

    return table


def create_summary_panel(events: list[Event]) -> Panel:
    """Create a summary panel with stats."""

    text = Text()

    # Count various event types
    chatting = 0
    tool_calls = 0
    mcps = set()

    for event in events:
        if event.type == "info":
            if "mcp_connection_manager" in event.namespace:
                message = event.message
                if ": " in message:
                    mcp_name = message.split(": ")[0]
                    mcps.add(mcp_name)

        progress_event = convert_log_event(event)
        if progress_event:
            if progress_event.action == ProgressAction.CHATTING:
                chatting += 1
            elif progress_event.action == ProgressAction.CALLING_TOOL:
                tool_calls += 1

    text.append("Summary:\n\n", style="bold")
    text.append("MCPs: ", style="bold")
    text.append(f"{', '.join(sorted(mcps))}\n", style="green")
    text.append("Chat Turns: ", style="bold")
    text.append(f"{chatting}\n", style="blue")
    text.append("Tool Calls: ", style="bold")
    text.append(f"{tool_calls}\n", style="magenta")

    return Panel(text, title="Event Statistics")


def main(log_file: str):
    """View MCP Agent events from a log file."""
    events = load_events(Path(log_file))
    console = Console()

    # Create layout
    console.print("\n")
    console.print(create_summary_panel(events))
    console.print("\n")
    console.print(Panel(create_event_table(events), title="Progress Events"))
    console.print("\n")


if __name__ == "__main__":
    typer.run(main)
