"""
Serve your app as an MCP server (scaffold).
"""

from __future__ import annotations

import asyncio
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.cli.core.utils import load_user_app


app = typer.Typer(help="Serve app as an MCP server")
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    script: Optional[str] = typer.Option(None, "--script"),
    transport: str = typer.Option("stdio", "--transport"),
    port: Optional[int] = typer.Option(None, "--port"),
    host: str = typer.Option("0.0.0.0", "--host"),
) -> None:
    """Start an MCP server for the user's app (minimal stdio/http)."""

    async def _run():
        app_obj = load_user_app(Path(script) if script else Path("agent.py"))
        await app_obj.initialize()
        mcp = create_mcp_server_for_app(app_obj)
        if transport == "stdio":
            await mcp.run_stdio_async()
        else:
            # http/sse: run uvicorn inside this process if requested
            try:
                import uvicorn  # type: ignore

                uvicorn_config = uvicorn.Config(
                    mcp.app, host=host, port=port or 8000, log_level="info"
                )
                server = uvicorn.Server(uvicorn_config)
                await server.serve()
            except Exception as e:
                typer.secho(
                    f"Failed to start HTTP server: {e}", fg=typer.colors.RED, err=True
                )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
