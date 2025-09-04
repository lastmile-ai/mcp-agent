"""
Command group entrypoints for the mcp-agent CLI (non-cloud).

Each module exposes a Typer app named `app` which is mounted by
`mcp_agent.cli.main` under an appropriate command group.
"""

from . import (
    chat,
    dev,
    invoke,
    serve,
    init,
    quickstart,
    config,
    keys,
    models,
    server,
    build,
    logs,
    doctor,
    configure,
    go,
    check,
)  # noqa: F401

__all__ = [
    "chat",
    "dev",
    "invoke",
    "serve",
    "init",
    "quickstart",
    "config",
    "keys",
    "models",
    "server",
    "build",
    "logs",
    "doctor",
    "configure",
    "go",
    "check",
]
