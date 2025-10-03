"""Token usage progress display using Rich Progress widget."""

import asyncio
from typing import Optional, Dict
from rich.console import Console
from rich.progress import Progress, TextColumn
from mcp_agent.console import console as default_console
from mcp_agent.tracing.token_counter import TokenNode, TokenUsage, TokenCounter
from contextlib import contextmanager


class TokenProgressDisplay:
    """Rich Progress-based display for token usage."""

    def __init__(self, token_counter: TokenCounter, console: Optional[Console] = None):
        """Initialize the token progress display."""
        self.console = console or default_console
        self.token_counter = token_counter
        self._taskmap: Dict[str, int] = {}
        self._watch_ids = []

        # Create progress display with custom columns
        self._progress = Progress(
            TextColumn("[bold cyan]Token Usage", justify="left"),
            TextColumn("{task.fields[node_info]:<30}", style="white"),
            TextColumn("{task.fields[tokens]:>10}", style="bold green"),
            TextColumn("{task.fields[cost]:>10}", style="bold yellow"),
            console=self.console,
            transient=False,
            refresh_per_second=10,
        )
        self._paused = False
        self._total_task_id = None

    def start(self):
        """Start the progress display and register watches."""
        self._progress.start()

        # Add a task for the total
        self._total_task_id = self._progress.add_task(
            "", total=None, node_info="[bold]TOTAL", tokens="0", cost="$0.0000"
        )

        # Register watch on app node for aggregate totals
        # Schedule async watch registration (robust against timing of root creation)
        asyncio.create_task(self._register_watch())

    async def _register_watch(self):
        """Register watch asynchronously."""
        try:
            app_node = await self.token_counter.get_app_node()
            if app_node:
                watch_id = await self.token_counter.watch(
                    callback=self._on_token_update,
                    node=app_node,
                    threshold=1,
                    throttle_ms=100,
                )
                self._watch_ids.append(watch_id)
            else:
                # Fallback: watch any app node that appears later
                watch_id = await self.token_counter.watch(
                    callback=self._on_token_update,
                    node_type="app",
                    threshold=1,
                    throttle_ms=100,
                )
                self._watch_ids.append(watch_id)
        except Exception:
            # Silently ignore display registration failures
            pass

    async def _unregister_watches(self):
        """Unregister all watches asynchronously."""
        for watch_id in self._watch_ids:
            await self.token_counter.unwatch(watch_id)
        self._watch_ids.clear()

    def stop(self):
        """Stop the progress display and unregister watches."""
        # Schedule async unwatch
        if self._watch_ids:
            asyncio.create_task(self._unregister_watches())

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

    def _format_tokens(self, tokens: int) -> str:
        """Format token count with thousands separator."""
        return f"{tokens:,}"

    def _format_cost(self, cost: float) -> str:
        """Format cost in USD."""
        return f"${cost:.4f}"

    async def _on_token_update(self, node: TokenNode, usage: TokenUsage):
        """Handle token usage updates."""
        # Only update the total summary
        summary = await self.token_counter.get_summary()
        self._progress.update(
            self._total_task_id,
            node_info="[bold]TOTAL",
            tokens=self._format_tokens(summary.usage.total_tokens),
            cost=self._format_cost(summary.cost),
        )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
