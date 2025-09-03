"""
Keys management (scaffold): show/set/unset.
"""

from __future__ import annotations

import os
import typer
from rich.console import Console


app = typer.Typer(help="Manage provider API keys")
console = Console()


PROVIDERS = [
    ("openai", "OPENAI_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("google", "GOOGLE_API_KEY"),
]


@app.command("show")
def show() -> None:
    """Show keys from environment (scaffold)."""
    for prov, env in PROVIDERS:
        val = os.environ.get(env)
        tail = f"…{val[-4:]}" if val else ""
        console.print(f"{prov}: {tail}")


@app.command("set")
def set_key(provider: str, key: str) -> None:
    """Scaffold: export to environment for current process only."""
    mapping = {p: e for p, e in PROVIDERS}
    env = mapping.get(provider)
    if not env:
        typer.secho("Unknown provider", fg=typer.colors.RED, err=True)
        raise typer.Exit(6)
    os.environ[env] = key
    console.print(f"Set {provider} key (session)")


@app.command("unset")
def unset(provider: str) -> None:
    mapping = {p: e for p, e in PROVIDERS}
    env = mapping.get(provider)
    if not env:
        typer.secho("Unknown provider", fg=typer.colors.RED, err=True)
        raise typer.Exit(6)
    os.environ.pop(env, None)
    console.print(f"Unset {provider} key (session)")


