"""Rich-based progress display for MCP Agent."""

from typing import Optional
from rich.console import Console
from mcp_agent.console import console as default_console
from mcp_agent.event_progress import ProgressEvent, ProgressAction
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from contextlib import contextmanager


class RichProgressDisplay:
    """Rich-based display for progress events."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the progress display."""
        self.console = console or default_console
        self._taskmap = {}
        self._progress = Progress(
            TimeElapsedColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=15),
            TextColumn(text_format="{task.fields[target]:<18}", style="Blue"),
            TextColumn(text_format="{task.fields[details]}"),
            console=self.console,
            transient=False,
        )
        self._paused = False

    def start(self):
        """start"""
        # task_id = self._progress.add_task(
        #     "[white]...mcp-agent...",
        #     total=None,
        #     target="mcp-agent app",
        #     details="",
        #     task_name="default",
        # )
        # self._taskmap["default"] = task_id
        self._progress.start()

    def stop(self):
        """stop"""
        self._progress.stop()

    def pause(self):
        """Pause the progress display."""
        if not self._paused:
            self._paused = True

            for task in self._progress.tasks:
                task.visible = False
            self._progress.stop()

    def resume(self):
        """Resume the progress display."""
        if self._paused:
            for task in self._progress.tasks:
                task.visible = True
            self._paused = False
            self._progress.start()

    @contextmanager
    def paused(self):
        """Context manager for temporarily pausing the display."""
        self.pause()
        try:
            yield
        finally:
            self.resume()

    def _get_action_style(self, action: ProgressAction) -> str:
        """Map actions to appropriate styles."""
        return {
            ProgressAction.STARTING: "black on yellow",
            ProgressAction.INITIALIZED: "black on green",
            ProgressAction.RUNNING: "black on green",
            ProgressAction.CHATTING: "white on dark_blue",
            ProgressAction.ROUTING: "white on dark_blue",
            ProgressAction.CALLING_TOOL: "white on dark_magenta",
            ProgressAction.FINISHED: "black on green",
            ProgressAction.SHUTDOWN: "black on red",
            ProgressAction.AGGREGATOR_INITIALIZED: "black on green",
        }.get(action, "white")

    def update(self, event: ProgressEvent) -> None:
        """Update the progress display with a new event."""
        task_name = event.agent_name or "default"

        # Create new task if needed
        if task_name not in self._taskmap:
            task_id = self._progress.add_task(
                "",
                total=None,
                target=f"{event.target}",
                details=f"{event.agent_name}",
            )
            self._taskmap[task_name] = task_id
        else:
            task_id = self._taskmap[task_name]

        # For FINISHED events, mark the task as complete
        if event.action == ProgressAction.FINISHED:
            self._progress.update(task_id, total=100, completed=100)
            self._taskmap.pop(task_name)

        # Update the task with new information
        self._progress.update(
            task_id,
            description=f"[{self._get_action_style(event.action)}]{event.action.value:<15}",
            target=event.target,
            details=event.details if event.details else "",
            task_name=task_name,
        )
