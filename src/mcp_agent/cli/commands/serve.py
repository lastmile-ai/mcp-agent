"""
Serve your app as an MCP server with comprehensive options.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Optional, List
from pathlib import Path
import os

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.server.app_server import create_mcp_server_for_app
from mcp_agent.cli.core.utils import load_user_app, detect_default_script
from mcp_agent.config import get_settings


app = typer.Typer(help="Serve app as an MCP server")
console = Console(stderr=True)


class ServerMonitor:
    """Monitor for server statistics and health."""

    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.active_connections = 0
        self.start_time = None
        self.last_request = None

    def get_stats(self) -> dict:
        """Get current statistics."""
        import time

        uptime = 0
        if self.start_time:
            uptime = int(time.time() - self.start_time)

        return {
            "requests": self.requests,
            "errors": self.errors,
            "connections": self.active_connections,
            "uptime": uptime,
            "last_request": self.last_request,
        }


def _create_status_table(monitor: ServerMonitor, transport: str, address: str) -> Table:
    """Create a status table for the server."""
    stats = monitor.get_stats()

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Transport", transport.upper())
    table.add_row("Address", address)
    table.add_row("Status", "[green]● Running[/green]")
    table.add_row("Uptime", f"{stats['uptime']}s")
    table.add_row("Requests", str(stats["requests"]))
    table.add_row("Errors", str(stats["errors"]))
    table.add_row("Connections", str(stats["active_connections"]))

    return table


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    script: Optional[str] = typer.Option(
        None, "--script", "-s", help="Python script with MCPApp"
    ),
    transport: str = typer.Option(
        "stdio", "--transport", "-t", help="Transport: stdio|http|sse"
    ),
    port: Optional[int] = typer.Option(
        None, "--port", "-p", help="Port for HTTP/SSE server"
    ),
    host: str = typer.Option(
        "0.0.0.0", "--host", "-H", help="Host for HTTP/SSE server"
    ),
    reload: bool = typer.Option(
        False, "--reload", "-r", help="Auto-reload on code changes"
    ),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of worker processes (HTTP only)"
    ),
    env: Optional[List[str]] = typer.Option(
        None, "--env", "-e", help="Environment variables (KEY=value)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Config file path"
    ),
    show_tools: bool = typer.Option(
        False, "--show-tools", help="Display available tools on startup"
    ),
    monitor: bool = typer.Option(
        False, "--monitor", "-m", help="Enable monitoring dashboard"
    ),
    ssl_certfile: Optional[Path] = typer.Option(
        None, "--ssl-certfile", help="Path to SSL certificate file (HTTP/SSE)"
    ),
    ssl_keyfile: Optional[Path] = typer.Option(
        None, "--ssl-keyfile", help="Path to SSL private key file (HTTP/SSE)"
    ),
) -> None:
    """
    Start an MCP server for your app.

    Examples:
        mcp-agent dev serve --script agent.py
        mcp-agent dev serve --transport http --port 8000
        mcp-agent dev serve --reload --debug
    """

    if ctx.invoked_subcommand:
        return

    # Set environment variables if provided
    if env:
        for env_pair in env:
            if "=" in env_pair:
                key, value = env_pair.split("=", 1)
                os.environ[key] = value
                if debug:
                    console.print(f"[dim]Set {key}={value}[/dim]")

    # Load configuration path is handled after loading app by overriding app settings

    async def _run():
        # Load the app (auto-detect main.py preferred)
        script_path = detect_default_script(Path(script) if script else None)

        if not script_path.exists():
            console.print(f"[red]Script not found: {script_path}[/red]")
            console.print(
                "\n[dim]Create a main.py (preferred) or agent.py file, or specify --script[/dim]"
            )
            raise typer.Exit(1)

        console.print("\n[bold cyan]🚀 MCP-Agent Server[/bold cyan]")
        console.print(f"Script: [green]{script_path}[/green]")

        # Load settings from config if provided
        settings_override = None
        if config:
            try:
                from mcp_agent.config import get_settings as _get_settings

                settings_override = _get_settings(config_path=str(config))
                console.print(f"Config: [green]{config}[/green]")
            except Exception as _e:
                console.print(f"[red]Failed to load config: {_e}[/red]")
                if debug:
                    import traceback

                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                raise typer.Exit(1)

        try:
            app_obj = load_user_app(script_path, settings_override=settings_override)
        except Exception as e:
            console.print(f"[red]Failed to load app: {e}[/red]")
            if debug:
                import traceback

                console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(1)
        # Initialize the app
        await app_obj.initialize()

        # Create MCP server
        mcp = create_mcp_server_for_app(app_obj)

        # Show server info
        info_table = Table(show_header=False, box=None)
        info_table.add_column("Property", style="cyan")
        info_table.add_column("Value")

        info_table.add_row("App Name", app_obj.name)
        info_table.add_row("Transport", transport.upper())

        if transport == "stdio":
            info_table.add_row("Mode", "Standard I/O")
        else:
            address = f"{host}:{port or 8000}"
            info_table.add_row("Address", f"http://{address}")
            if transport == "sse":
                info_table.add_row("SSE Endpoint", f"http://{address}/sse")
            elif transport == "http":
                info_table.add_row("HTTP Endpoint", f"http://{address}/mcp")

        # Show registered components
        if hasattr(app_obj, "workflows") and app_obj.workflows:
            info_table.add_row("Workflows", str(len(app_obj.workflows)))

        if hasattr(app_obj, "agents") and app_obj.agents:
            info_table.add_row("Agents", str(len(app_obj.agents)))

        settings = get_settings()
        if settings.mcp and settings.mcp.servers:
            info_table.add_row("MCP Servers", str(len(settings.mcp.servers)))

        console.print(
            Panel(
                info_table,
                title="[bold]Server Information[/bold]",
                border_style="green",
            )
        )

        # Show available tools if requested
        if show_tools:
            try:
                # Get tools from the MCP server
                tools_list = []
                if hasattr(mcp, "list_tools"):
                    tools_response = await mcp.list_tools()
                    if tools_response and hasattr(tools_response, "tools"):
                        tools_list = tools_response.tools

                if tools_list:
                    console.print("\n[bold]Available Tools:[/bold]")
                    tools_table = Table(show_header=True, header_style="cyan")
                    tools_table.add_column("Tool", style="green")
                    tools_table.add_column("Description")

                    for tool in tools_list[:10]:  # Show first 10
                        desc = (
                            tool.description[:60] + "..."
                            if len(tool.description) > 60
                            else tool.description
                        )
                        tools_table.add_row(tool.name, desc)

                    if len(tools_list) > 10:
                        tools_table.add_row("...", f"and {len(tools_list) - 10} more")

                    console.print(tools_table)
            except Exception:
                pass

        # Set up monitoring if requested
        server_monitor = ServerMonitor() if monitor else None

        # Handle shutdown gracefully
        shutdown_event = asyncio.Event()

        def signal_handler(sig, frame):
            console.print("\n[yellow]Shutting down server...[/yellow]")
            shutdown_event.set()
            os._exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start server based on transport
        if transport == "stdio":
            console.print("\n[green]Server running on STDIO[/green]")
            console.print(
                "[dim]Ready for MCP client connections via standard I/O[/dim]\n"
            )

            if debug:
                console.print(
                    "[yellow]Debug mode: Messages will be logged to stderr[/yellow]\n"
                )

            try:
                await mcp.run_stdio_async()
            except Exception as e:
                if "Broken pipe" not in str(e):
                    console.print(f"[red]Server error: {e}[/red]")
                    if debug:
                        import traceback

                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

        elif transport in ["http", "sse"]:
            # HTTP/SSE server
            try:
                import uvicorn

                # Configure uvicorn
                uvicorn_config = uvicorn.Config(
                    mcp.streamable_http_app if transport == "http" else mcp.sse_app,
                    host=host,
                    port=port or 8000,
                    log_level="debug" if debug else "info",
                    reload=reload,
                    workers=workers
                    if not reload
                    else 1,  # Can't use multiple workers with reload
                    access_log=debug,
                )

                # Apply TLS if provided
                if ssl_certfile and ssl_keyfile:
                    uvicorn_config.ssl_certfile = str(ssl_certfile)
                    uvicorn_config.ssl_keyfile = str(ssl_keyfile)

                server = uvicorn.Server(uvicorn_config)

                console.print(f"\n[green]Server running on {transport.upper()}[/green]")
                console.print(f"[bold]URL:[/bold] http://{host}:{port or 8000}")

                if transport == "sse":
                    console.print(f"[bold]SSE:[/bold] http://{host}:{port or 8000}/sse")
                elif transport == "http":
                    console.print(
                        f"[bold]HTTP:[/bold] http://{host}:{port or 8000}/mcp"
                    )

                console.print("\n[dim]Press Ctrl+C to stop the server[/dim]\n")

                # Start monitoring display if enabled
                if monitor and server_monitor:
                    import time as _time

                    server_monitor.start_time = _time.time()

                    async def update_monitor():
                        with Live(auto_refresh=True, refresh_per_second=1) as live:
                            while not shutdown_event.is_set():
                                table = _create_status_table(
                                    server_monitor,
                                    transport,
                                    f"http://{host}:{port or 8000}",
                                )
                                live.update(
                                    Panel(
                                        table,
                                        title="[bold]Server Monitor[/bold]",
                                        border_style="cyan",
                                    )
                                )
                                await asyncio.sleep(1)

                    asyncio.create_task(update_monitor())

                await server.serve()

            except ImportError:
                console.print("[red]uvicorn not installed[/red]")
                console.print("\n[dim]Install with: pip install uvicorn[/dim]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(
                    f"[red]Failed to start {transport.upper()} server: {e}[/red]"
                )
                if debug:
                    import traceback

                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                raise typer.Exit(1)

        else:
            console.print(f"[red]Unknown transport: {transport}[/red]")
            console.print("[dim]Supported: stdio, http, sse[/dim]")
            raise typer.Exit(1)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        if debug:
            console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


@app.command()
def test(
    script: Optional[str] = typer.Option(None, "--script", "-s", help="Script to test"),
    timeout: float = typer.Option(5.0, "--timeout", "-t", help="Test timeout"),
) -> None:
    """Test if the server can be loaded and initialized."""
    script_path = detect_default_script(Path(script) if script else None)

    if not script_path.exists():
        console.print(f"[red]Script not found: {script_path}[/red]")
        console.print(
            "\n[dim]Create a main.py (preferred) or agent.py file, or specify --script[/dim]"
        )
        raise typer.Exit(1)

    console.print(f"\n[bold]Testing server: {script_path}[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        async def _test():
            # Load app
            task = progress.add_task("Loading app...", total=None)
            try:
                app_obj = load_user_app(script_path)
                progress.update(task, description="[green]✅ App loaded[/green]")
            except Exception as e:
                progress.update(task, description=f"[red]❌ Failed to load: {e}[/red]")
                raise typer.Exit(1)

            # Initialize app
            task = progress.add_task("Initializing app...", total=None)
            try:
                await asyncio.wait_for(app_obj.initialize(), timeout=timeout)
                progress.update(task, description="[green]✅ App initialized[/green]")
            except asyncio.TimeoutError:
                progress.update(
                    task,
                    description=f"[red]❌ Initialization timeout ({timeout}s)[/red]",
                )
                raise typer.Exit(1)
            except Exception as e:
                progress.update(
                    task, description=f"[red]❌ Failed to initialize: {e}[/red]"
                )
                raise typer.Exit(1)

            # Create server
            task = progress.add_task("Creating MCP server...", total=None)
            try:
                create_mcp_server_for_app(app_obj)
                progress.update(task, description="[green]✅ Server created[/green]")
            except Exception as e:
                progress.update(
                    task, description=f"[red]❌ Failed to create server: {e}[/red]"
                )
                raise typer.Exit(1)

            # Check components
            components = []
            if hasattr(app_obj, "workflows") and app_obj.workflows:
                components.append(f"{len(app_obj.workflows)} workflows")
            if hasattr(app_obj, "agents") and app_obj.agents:
                components.append(f"{len(app_obj.agents)} agents")

            return app_obj, components

        try:
            app_obj, components = asyncio.run(_test())

            console.print("\n[green bold]✅ Server test passed![/green bold]\n")

            # Show summary
            summary = Table(show_header=False, box=None)
            summary.add_column("Property", style="cyan")
            summary.add_column("Value")

            summary.add_row("App Name", app_obj.name)
            if hasattr(app_obj, "description") and app_obj.description:
                summary.add_row("Description", app_obj.description)
            if components:
                summary.add_row("Components", ", ".join(components))

            console.print(
                Panel(
                    summary, title="[bold]Server Summary[/bold]", border_style="green"
                )
            )

            console.print("\n[dim]Server is ready to run with:[/dim]")
            console.print(f"  [cyan]mcp-agent dev serve --script {script_path}[/cyan]")

        except Exception:
            console.print("\n[red bold]❌ Server test failed[/red bold]")
            raise typer.Exit(1)


@app.command()
def generate(
    name: str = typer.Option("my-mcp-server", "--name", "-n", help="Server name"),
    output: Path = typer.Option(
        Path("server.py"), "--output", "-o", help="Output file"
    ),
    template: str = typer.Option("basic", "--template", "-t", help="Template to use"),
) -> None:
    """Generate a new MCP server script from template."""
    from importlib import resources

    console.print(f"\n[bold]Generating MCP server: {name}[/bold]\n")

    # Load template
    template_map = {
        "basic": "basic_agent_server.py",
        "workflow": "basic_agent_server.py",
        "parallel": "basic_agent_server.py",
    }

    template_file = template_map.get(template, "basic_agent_server.py")

    try:
        with (
            resources.files("mcp_agent.data.templates")
            .joinpath(template_file)
            .open() as f
        ):
            content = f.read()
    except Exception as e:
        console.print(f"[red]Failed to load template: {e}[/red]")
        raise typer.Exit(1)

    # Customize template
    content = content.replace("basic_agent_server", name)
    content = content.replace("My basic agent server example", f"{name} MCP server")

    # Write file
    if output.exists():
        if not typer.confirm(f"{output} exists. Overwrite?"):
            raise typer.Exit(0)

    output.write_text(content)
    console.print(f"[green]✅ Generated server: {output}[/green]")

    # Make executable
    try:
        import stat

        output.chmod(output.stat().st_mode | stat.S_IEXEC)
    except Exception:
        pass

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"1. Edit the server: [cyan]{output}[/cyan]")
    console.print(
        f"2. Test the server: [cyan]mcp-agent dev serve test --script {output}[/cyan]"
    )
    console.print(
        f"3. Run the server: [cyan]mcp-agent dev serve --script {output}[/cyan]"
    )
    console.print(
        f"4. Or serve via HTTP: [cyan]mcp-agent dev serve --script {output} --transport http --port 8000[/cyan]"
    )
