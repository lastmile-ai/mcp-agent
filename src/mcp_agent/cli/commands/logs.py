"""
Local logs tailing (scaffold).
"""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console


app = typer.Typer(help="Tail local logs")
console = Console()


@app.callback(invoke_without_command=True)
def logs(
    file: Path = typer.Option(Path("mcp-agent.jsonl"), "--file"),
    follow: bool = typer.Option(False, "--follow"),
    limit: int = typer.Option(200, "--limit"),
) -> None:
    """Minimal file tailer (scaffold)."""
    try:
        lines = file.read_text(encoding="utf-8").splitlines()[-limit:]
    except Exception:
        lines = []
    for line in lines:
        console.print(line)
    if follow:
        console.print("--follow not implemented yet (scaffold)")


