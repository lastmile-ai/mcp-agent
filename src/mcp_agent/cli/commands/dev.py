"""
Run the user's app with live reload and diagnostics.
Loads the user's MCPApp from --script, performs simple preflight checks,
then starts the app. If watchdog is available, watches files and restarts on changes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import time

import typer
from rich.console import Console

from mcp_agent.app import MCPApp
from mcp_agent.cli.core.utils import load_user_app
from mcp_agent.config import get_settings


app = typer.Typer(help="Run app locally with diagnostics")
console = Console()


@app.callback(invoke_without_command=True)
def dev(script: Path = typer.Option(Path("agent.py"), "--script")) -> None:
    """Run the user's app script with optional live reload and preflight checks."""

    def _preflight_ok() -> bool:
        settings = get_settings()
        ok = True
        # check stdio commands
        servers = (settings.mcp.servers if settings.mcp else {}) or {}
        for name, s in servers.items():
            if s.transport == "stdio" and s.command and not shutil.which(s.command):
                console.print(
                    f"[yellow]Missing command for server '{name}': {s.command}[/yellow]"
                )
                ok = False
        return ok

    async def _run_once():
        app_obj = load_user_app(script)
        async with app_obj.run():
            console.print(f"Running {script}")
            # Sleep until cancelled
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

    # Simple preflight
    _ = _preflight_ok()

    # Try to use watchdog for live reload
    try:
        from watchdog.observers import Observer  # type: ignore
        from watchdog.events import FileSystemEventHandler  # type: ignore

        class _Handler(FileSystemEventHandler):
            def __init__(self):
                self.touched = False

            def on_modified(self, event):  # type: ignore
                self.touched = True

            def on_created(self, event):  # type: ignore
                self.touched = True

        loop = asyncio.get_event_loop()
        task = loop.create_task(_run_once())

        handler = _Handler()
        observer = Observer()
        observer.schedule(handler, path=str(script.parent), recursive=True)
        observer.start()
        console.print("Live reload enabled (watchdog)")
        try:
            while True:
                time.sleep(0.5)
                if handler.touched:
                    handler.touched = False
                    console.print("Change detected. Restarting...")
                    task.cancel()
                    try:
                        loop.run_until_complete(task)
                    except Exception:
                        pass
                    task = loop.create_task(_run_once())
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            task.cancel()
            try:
                loop.run_until_complete(task)
            except Exception:
                pass
    except Exception:
        # Fallback: run once
        try:
            asyncio.run(_run_once())
        except KeyboardInterrupt:
            pass
