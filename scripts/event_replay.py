#!/usr/bin/env python3
"""Event Replay Script

Replays events from a JSONL log file using rich_progress display.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import typer
from mcp_agent.event_progress import convert_log_event
from mcp_agent.logging.events import Event
from mcp_agent.logging.rich_progress import RichProgressDisplay


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


def main(log_file: str):
    """Replay MCP Agent events from a log file with progress display."""
    # Load events from file
    events = load_events(Path(log_file))

    # Initialize progress display
    progress = RichProgressDisplay()
    progress.start()

    try:
        # Process each event in sequence
        for event in events:
            progress_event = convert_log_event(event)
            if progress_event:
                progress.update(progress_event)
                # Add a small delay to make the replay visible
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        progress.stop()


if __name__ == "__main__":
    typer.run(main)
