"""Rich-based progress display for MCP Agent."""

import asyncio
import time
from typing import Optional
from rich.console import Console
from mcp_agent.console import console as default_console
from mcp_agent.logging.event_progress import ProgressEvent, ProgressAction
from rich.progress import Progress, SpinnerColumn, TextColumn
from contextlib import contextmanager


class RichProgressDisplay:
    """Rich-based display for progress events with optional token tracking."""

    def __init__(self, console: Optional[Console] = None, token_counter=None):
        """Initialize the progress display.

        Args:
            console: Rich console to use
            token_counter: Optional TokenCounter instance for token tracking
        """
        self.console = console or default_console
        self._taskmap = {}
        self._token_counter = token_counter
        self._token_task_id = None
        self._token_watch_id = None

        # Create progress display
        self._progress = Progress(
            SpinnerColumn(spinner_name="simpleDotsScrolling"),
            TextColumn(
                "[progress.description]{task.description}|",
            ),
            TextColumn(text_format="{task.fields[target]:<16}", style="Bold Blue"),
            TextColumn(text_format="{task.fields[details]}", style="dim white"),
            console=self.console,
            transient=False,
        )
        self._paused = False

    def start(self):
        """Start the progress display and optionally token tracking."""
        self._progress.start()

        # Always add a token tracking row if token counter is available
        if self._token_counter:
            self._start_token_tracking()

    def stop(self):
        """Stop the progress display and token tracking."""
        # Stop token tracking if active
        if self._token_watch_id and self._token_counter:
            # Schedule async unwatch
            asyncio.create_task(self._unwatch_async())

    async def _unwatch_async(self):
        """Unwatch the token counter asynchronously."""
        if self._token_watch_id and self._token_counter:
            await self._token_counter.unwatch(self._token_watch_id)
            self._token_watch_id = None

        self._progress.stop()

    def _start_token_tracking(self):
        """Start tracking token usage."""
        # Add a task for token display
        self._token_task_id = self._progress.add_task(
            "",  # description (empty for consistency)
            target="usage",
            details="",
            total=None,
        )

        # Set initial description with token data
        self._progress.update(
            self._token_task_id,
            description="[bold cyan]Tokens      ",
            details="0 tokens | $0.0000",
        )

        # Try to register watch immediately, but don't fail if root doesn't exist yet
        self._try_register_watch()

    def _try_register_watch(self):
        """Try to register the token watch if root node exists."""
        if self._token_watch_id or not self._token_counter:
            return  # Already registered or no counter

        # Check if root node exists now
        if hasattr(self._token_counter, "_root") and self._token_counter._root:
            # Schedule async watch registration
            asyncio.create_task(self._register_watch_async())

    async def _register_watch_async(self):
        """Register the token watch asynchronously."""
        if hasattr(self._token_counter, "_root") and self._token_counter._root:
            self._token_watch_id = await self._token_counter.watch(
                callback=self._on_token_update,
                node=self._token_counter._root,
                threshold=1,
                throttle_ms=100,
            )
            # Get initial summary and update display
            await self._update_initial_token_display()

    async def _update_initial_token_display(self):
        """Update initial token display."""
        initial_summary = await self._token_counter.get_summary()
        if initial_summary.usage.total_tokens > 0:
            self._progress.update(
                self._token_task_id,
                description="[bold cyan]Tokens      ",
                details=f"{initial_summary.usage.total_tokens:,} tokens | ${initial_summary.cost:.4f}",
            )

    async def _on_token_update(self, node, usage):
        """Handle token usage updates."""
        summary = await self._token_counter.get_summary()
        self._progress.update(
            self._token_task_id,
            description="[bold cyan]Tokens      ",
            details=f"{summary.usage.total_tokens:,} tokens | ${summary.cost:.4f}",
        )

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
            ProgressAction.STARTING: "bold yellow",
            ProgressAction.LOADED: "dim green",
            ProgressAction.INITIALIZED: "dim green",
            ProgressAction.RUNNING: "black on green",
            ProgressAction.CHATTING: "bold blue",
            ProgressAction.ROUTING: "bold blue",
            ProgressAction.PLANNING: "bold blue",
            ProgressAction.READY: "dim green",
            ProgressAction.CALLING_TOOL: "bold magenta",
            ProgressAction.FINISHED: "black on green",
            ProgressAction.SHUTDOWN: "black on red",
            ProgressAction.AGGREGATOR_INITIALIZED: "bold green",
            ProgressAction.FATAL_ERROR: "black on red",
        }.get(action, "white")

    def update(self, event: ProgressEvent) -> None:
        """Update the progress display with a new event."""
        # Try to register token watch if we haven't yet
        if (
            self._token_counter
            and self._token_task_id is not None
            and not self._token_watch_id
        ):
            self._try_register_watch()

        task_name = event.agent_name or "default"

        # Create new task if needed
        if task_name not in self._taskmap:
            task_id = self._progress.add_task(
                "",
                total=None,
                target=f"{event.target or task_name}",
                details=f"{event.agent_name or ''}",
            )
            self._taskmap[task_name] = task_id
        else:
            task_id = self._taskmap[task_name]

        # Ensure no None values in the update
        self._progress.update(
            task_id,
            description=f"[{self._get_action_style(event.action)}]{event.action.value:<15}",
            target=event.target or task_name,
            details=event.details or "",
            task_name=task_name,
        )

        if event.action in (
            ProgressAction.INITIALIZED,
            ProgressAction.READY,
            ProgressAction.LOADED,
        ):
            self._progress.update(task_id, completed=100, total=100)
        elif event.action == ProgressAction.FINISHED:
            self._progress.update(
                task_id,
                completed=100,
                total=100,
                details=f" / Elapsed Time {time.strftime('%H:%M:%S', time.gmtime(self._progress.tasks[task_id].elapsed))}",
            )
            for task in self._progress.tasks:
                # Never hide the token display task
                if task.id != task_id and task.id != self._token_task_id:
                    task.visible = False
        elif event.action == ProgressAction.FATAL_ERROR:
            self._progress.update(
                task_id,
                completed=100,
                total=100,
                details=f" / {event.details}",
            )
            for task in self._progress.tasks:
                # Never hide the token display task
                if task.id != task_id and task.id != self._token_task_id:
                    task.visible = False
        else:
            self._progress.reset(task_id)
