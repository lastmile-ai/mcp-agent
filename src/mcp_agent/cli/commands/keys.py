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
    """Show keys from environment and config (masked)."""
    from mcp_agent.config import get_settings

    settings = get_settings()
    for prov, env in PROVIDERS:
        env_val = os.environ.get(env)
        cfg = getattr(settings, prov, None)
        cfg_val = getattr(cfg, "api_key", None) if cfg else None
        active = cfg_val or env_val
        tail = f"…{active[-4:]}" if active else ""
        source = "config" if cfg_val else ("env" if env_val else "none")
        console.print(f"{prov}: {tail} ({source})")


@app.command("set")
def set_key(provider: str, key: str) -> None:
    """Set key in secrets file (and session env)."""
    import yaml
    from mcp_agent.config import Settings

    mapping = {p: e for p, e in PROVIDERS}
    env = mapping.get(provider)
    if not env:
        typer.secho("Unknown provider", fg=typer.colors.RED, err=True)
        raise typer.Exit(6)

    # Update environment for current process
    os.environ[env] = key

    # Persist to secrets yaml
    sec_path = Settings.find_secrets()
    if not sec_path:
        # create under .mcp-agent
        from pathlib import Path as _Path

        sec_dir = _Path.cwd() / ".mcp-agent"
        sec_dir.mkdir(exist_ok=True)
        sec_path = sec_dir / "mcp_agent.secrets.yaml"
        data = {}
    else:
        try:
            data = yaml.safe_load(sec_path.read_text()) or {}
        except Exception:
            data = {}

    if provider not in data or not isinstance(data.get(provider), dict):
        data[provider] = {}
    data[provider]["api_key"] = key

    try:
        sec_path.write_text(yaml.safe_dump(data, sort_keys=False))
        console.print(f"Persisted {provider} key to {sec_path}")
    except Exception as e:
        typer.secho(f"Failed to write secrets: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(5)


@app.command("unset")
def unset(provider: str) -> None:
    import yaml
    from mcp_agent.config import Settings

    mapping = {p: e for p, e in PROVIDERS}
    env = mapping.get(provider)
    if not env:
        typer.secho("Unknown provider", fg=typer.colors.RED, err=True)
        raise typer.Exit(6)
    os.environ.pop(env, None)

    sec_path = Settings.find_secrets()
    if sec_path and sec_path.exists():
        try:
            data = yaml.safe_load(sec_path.read_text()) or {}
            sect = data.get(provider)
            if isinstance(sect, dict) and "api_key" in sect:
                sect.pop("api_key", None)
                data[provider] = sect
                sec_path.write_text(yaml.safe_dump(data, sort_keys=False))
                console.print(f"Removed {provider} key from {sec_path}")
        except Exception:
            pass
    console.print(f"Unset {provider} key (session)")
