"""
Serve your app as an MCP server (scaffold).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from mcp_agent.app import MCPApp
from mcp_agent.server.app_server import create_mcp_server_for_app


app = typer.Typer(help="Serve app as an MCP server")
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    script: Optional[str] = typer.Option(None, "--script"),
    transport: str = typer.Option("stdio", "--transport"),
    port: Optional[int] = typer.Option(None, "--port"),
) -> None:
    """Start an MCP server for the user's app (minimal stdio/http)."""

    async def _run():
        mcp_app = MCPApp(name="mcp-agent server")
        await mcp_app.initialize()
        mcp = create_mcp_server_for_app(mcp_app)
        if transport == "stdio":
            # FastMCP will manage stdio run within its own runner when launched by client
            console.print("MCP server (stdio) initialized.")
        else:
            # http/sse: run uvicorn inside this process if requested
            try:
                import uvicorn  # type: ignore

                host = "0.0.0.0"
                uvicorn_config = uvicorn.Config(mcp.app, host=host, port=port or 8000, log_level="info")
                server = uvicorn.Server(uvicorn_config)
                await server.serve()
            except Exception as e:
                typer.secho(f"Failed to start HTTP server: {e}", fg=typer.colors.RED, err=True)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


