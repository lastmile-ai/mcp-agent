"""Token usage progress display using Rich Progress widget."""

import asyncio
import logging
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
        self._generation = 0
        self._running = False
        self._background_tasks = set()

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
        if self._running:
            return
        asyncio.get_running_loop()
        self._running = True
        self._generation += 1
        self._progress.start()

        # Add a task for the total
        self._total_task_id = self._progress.add_task(
            "", total=None, node_info="[bold]TOTAL", tokens="0", cost="$0.0000"
        )

        # Register watch on app node for aggregate totals
        # Schedule async watch registration (robust against timing of root creation)
        self._spawn(self._register_watch(self._generation))

    def _spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task):
        self._background_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).warning(
                "Token display cleanup failed", exc_info=task.exception()
            )

    async def _register_watch(self, generation):
        """Register watch asynchronously."""

        async def on_update(node, usage):
            if self._running and generation == self._generation:
                await self._on_token_update(node, usage, generation)

        try:
            app_node = await self.token_counter.get_app_node()
            if not self._running or generation != self._generation:
                return
            if app_node:
                watch_id = await self.token_counter.watch(
                    callback=on_update,
                    node=app_node,
                    threshold=1,
                    throttle_ms=100,
                )

            else:
                # Fallback: watch any app node that appears later
                watch_id = await self.token_counter.watch(
                    callback=on_update,
                    node_type="app",
                    threshold=1,
                    throttle_ms=100,
                )

            if self._running and generation == self._generation:
                self._watch_ids.append(watch_id)
            else:
                await self._unregister_watches([watch_id])
        except Exception:
            # Silently ignore display registration failures
            pass

    async def _unregister_watches(self, watch_ids):
        """Unregister all watches asynchronously."""
        for watch_id in watch_ids:
            try:
                await self.token_counter.unwatch(watch_id)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Token display unwatch failed", exc_info=True
                )

    def stop(self):
        """Stop rendering and schedule cleanup; this synchronous method does not wait."""
        if self._watch_ids:
            asyncio.get_running_loop()
        self._running = False
        self._generation += 1
        watch_ids, self._watch_ids = self._watch_ids, []
        # Detach this generation before yielding to asynchronous cleanup.
        if watch_ids:
            self._spawn(self._unregister_watches(watch_ids))

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

    async def _on_token_update(
        self, node: TokenNode, usage: TokenUsage, generation=None
    ):
        """Handle token usage updates."""
        # Only update the total summary
        summary = await self.token_counter.get_summary()
        if generation is not None and (
            not self._running or generation != self._generation
        ):
            return
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
