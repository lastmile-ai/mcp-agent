"""
Run the user's app with live reload and diagnostics.
Loads the user's MCPApp from --script, performs simple preflight checks,
then starts the app. If watchdog is available, watches files and restarts on changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import shutil

import typer
from rich.console import Console

from mcp_agent.config import get_settings
from mcp_agent.cli.core.utils import detect_default_script


app = typer.Typer(help="Run app locally with diagnostics")
console = Console()


@app.callback(invoke_without_command=True)
def dev(script: Path = typer.Option(None, "--script")) -> None:
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

    def _run_script() -> subprocess.Popen:
        """Run the script as a subprocess."""
        console.print(f"Running {script}")
        # Run the script with the same Python interpreter
        return subprocess.Popen(
            [sys.executable, str(script)],
            stdout=None,  # Inherit stdout
            stderr=None,  # Inherit stderr
            stdin=None,  # Inherit stdin
        )

    # Resolve script path with auto-detection (main.py preferred)
    script = detect_default_script(script)

    # Simple preflight
    _ = _preflight_ok()

    # Try to use watchdog for live reload
    try:
        from watchdog.observers import Observer  # type: ignore
        from watchdog.events import FileSystemEventHandler  # type: ignore
        import time

        class _Handler(FileSystemEventHandler):
            def __init__(self):
                self.touched = False

            def on_modified(self, event):  # type: ignore
                if not event.is_directory:
                    self.touched = True

            def on_created(self, event):  # type: ignore
                if not event.is_directory:
                    self.touched = True

        handler = _Handler()
        observer = Observer()
        observer.schedule(handler, path=str(script.parent), recursive=True)
        observer.start()
        console.print("Live reload enabled (watchdog)")

        # Start the script
        process = _run_script()

        try:
            while True:
                time.sleep(0.5)

                # Check if process died
                if process.poll() is not None:
                    console.print(
                        f"[red]Process exited with code {process.returncode}[/red]"
                    )
                    break

                # Check for file changes
                if handler.touched:
                    handler.touched = False
                    console.print("Change detected. Restarting...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process = _run_script()

        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping...[/yellow]")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            observer.stop()
            observer.join()

    except ImportError:
        # Fallback: run once without watchdog
        console.print(
            "[yellow]Watchdog not installed. Running without live reload.[/yellow]"
        )
        process = _run_script()
        try:
            process.wait()
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping...[/yellow]")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
