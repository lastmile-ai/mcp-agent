"""
Local server helpers: add/import/list/test with comprehensive server recipes.
"""

from __future__ import annotations

from typing import Optional
import json

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from mcp_agent.config import Settings, MCPServerSettings, MCPSettings, get_settings
from mcp_agent.cli.utils.importers import import_servers_from_mcp_json
from mcp_agent.core.context import cleanup_context


app = typer.Typer(help="Local server helpers")
console = Console()


# Comprehensive server recipes database
SERVER_RECIPES = {
    # Core MCP servers
    "filesystem": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "description": "File system access (read/write files and directories)",
        "category": "core",
    },
    "fetch": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "description": "Web fetching capabilities",
        "category": "core",
    },
    "roots": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-roots"],
        "description": "Roots index server (mount multiple directories as resources)",
        "category": "core",
    },
    # Development tools
    "github": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "description": "GitHub API integration (requires GITHUB_PERSONAL_ACCESS_TOKEN)",
        "category": "development",
        "env_required": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
    },
    "gitlab": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gitlab"],
        "description": "GitLab API integration",
        "category": "development",
        "env_required": ["GITLAB_API_TOKEN"],
    },
    "git": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-git"],
        "description": "Git repository operations",
        "category": "development",
    },
    # Search and knowledge
    "brave-search": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "description": "Brave search API (requires BRAVE_API_KEY)",
        "category": "search",
        "env_required": ["BRAVE_API_KEY"],
    },
    "google-search": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-server-google-search"],
        "description": "Google search integration",
        "category": "search",
        "env_required": ["GOOGLE_API_KEY", "GOOGLE_CSE_ID"],
    },
    "wikipedia": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-wikipedia"],
        "description": "Wikipedia content access",
        "category": "knowledge",
    },
    "arxiv": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-arxiv"],
        "description": "arXiv paper search and retrieval",
        "category": "knowledge",
    },
    # Communication
    "slack": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "description": "Slack workspace integration (requires SLACK_BOT_TOKEN)",
        "category": "communication",
        "env_required": ["SLACK_BOT_TOKEN"],
    },
    "discord": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-discord"],
        "description": "Discord bot integration",
        "category": "communication",
        "env_required": ["DISCORD_BOT_TOKEN"],
    },
    "email": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-email"],
        "description": "Email sending capabilities",
        "category": "communication",
        "env_required": ["SMTP_HOST", "SMTP_USER", "SMTP_PASS"],
    },
    # Databases
    "postgres": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "description": "PostgreSQL database operations",
        "category": "database",
        "env_required": ["POSTGRES_URL"],
    },
    "sqlite": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "database.db"],
        "description": "SQLite database operations",
        "category": "database",
    },
    "mongodb": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-mongodb"],
        "description": "MongoDB database operations",
        "category": "database",
        "env_required": ["MONGODB_URI"],
    },
    # Cloud providers
    "aws": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-aws"],
        "description": "AWS services integration",
        "category": "cloud",
        "env_required": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    },
    "gcp": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-gcp"],
        "description": "Google Cloud Platform integration",
        "category": "cloud",
        "env_required": ["GOOGLE_APPLICATION_CREDENTIALS"],
    },
    "azure": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-azure"],
        "description": "Azure services integration",
        "category": "cloud",
        "env_required": [
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
        ],
    },
    # Productivity
    "notion": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-notion"],
        "description": "Notion workspace integration",
        "category": "productivity",
        "env_required": ["NOTION_API_KEY"],
    },
    "obsidian": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-obsidian", "~/Documents/Obsidian"],
        "description": "Obsidian vault integration",
        "category": "productivity",
    },
    "todoist": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-todoist"],
        "description": "Todoist task management",
        "category": "productivity",
        "env_required": ["TODOIST_API_TOKEN"],
    },
    # Development utilities
    "docker": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-docker"],
        "description": "Docker container management",
        "category": "development",
    },
    "kubernetes": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-k8s"],
        "description": "Kubernetes cluster management",
        "category": "development",
    },
    "terraform": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-terraform"],
        "description": "Terraform infrastructure management",
        "category": "development",
    },
    # Data and analytics
    "jupyter": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-jupyter"],
        "description": "Jupyter notebook execution",
        "category": "data",
    },
    "pandas": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-pandas"],
        "description": "Pandas dataframe operations",
        "category": "data",
    },
    "plotly": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-plotly"],
        "description": "Plotly visualization creation",
        "category": "data",
    },
    # Custom/experimental
    "shell": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-shell"],
        "description": "Shell command execution (use with caution)",
        "category": "system",
    },
    "python": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-python"],
        "description": "Python code execution environment",
        "category": "system",
    },
    "node": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-server-node"],
        "description": "Node.js code execution environment",
        "category": "system",
    },
}


def _load_config_yaml(path: Settings | None = None):
    import yaml

    cfg_path = Settings.find_config()
    data = {}
    if cfg_path and cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text()) or {}
        except Exception:
            data = {}
    return cfg_path, data


def _persist_server_entry(name: str, settings: MCPServerSettings) -> None:
    import yaml

    cfg_path, data = _load_config_yaml()
    # Ensure structure
    if "mcp" not in data:
        data["mcp"] = {}
    if "servers" not in data["mcp"] or data["mcp"]["servers"] is None:
        data["mcp"]["servers"] = {}
    # Build plain dict from settings
    entry = {
        "transport": settings.transport,
    }
    if settings.transport == "stdio":
        if settings.command:
            entry["command"] = settings.command
        if settings.args:
            entry["args"] = settings.args
        if settings.env:
            entry["env"] = settings.env
    else:
        if settings.url:
            entry["url"] = settings.url
        if settings.headers:
            entry["headers"] = settings.headers

    data["mcp"]["servers"][name] = entry

    # Decide path to write
    if not cfg_path:
        from pathlib import Path as _Path

        cfg_path = _Path("mcp_agent.config.yaml")

    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
    console.print(f"[green]✅[/green] Added server '[cyan]{name}[/cyan]' to {cfg_path}")


def _check_command_available(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    import shutil

    return shutil.which(cmd) is not None


@app.command("list")
def list_servers(
    available: bool = typer.Option(
        False, "--available", "-a", help="Show only available servers"
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category"
    ),
) -> None:
    """List configured servers."""
    settings = get_settings()
    servers = (settings.mcp.servers if settings.mcp else {}) or {}

    if not servers:
        console.print("[yellow]No servers configured[/yellow]")
        console.print(
            "\n[dim]Hint: Use [cyan]mcp-agent server add recipe <name>[/cyan] to add servers[/dim]"
        )
        console.print(
            "[dim]Or: [cyan]mcp-agent server recipes[/cyan] to see available recipes[/dim]"
        )
        return

    table = Table(title="Configured Servers", show_header=True, header_style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Transport")
    table.add_column("Target")
    table.add_column("Status", justify="center")

    for name, s in servers.items():
        target = s.url or s.command or ""
        if s.args and s.command:
            target = f"{s.command} {' '.join(s.args[:2])}..."

        # Check availability
        status = "❓"
        if s.transport == "stdio" and s.command:
            if _check_command_available(s.command.split()[0]):
                status = "✅"
            else:
                status = "❌"
        elif s.transport in ["http", "sse"] and s.url:
            status = "🌐"

        if not available or status in ["✅", "🌐"]:
            table.add_row(name, s.transport, target[:50], status)

    console.print(table)


@app.command("recipes")
def list_recipes(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category"
    ),
    show_env: bool = typer.Option(
        False, "--show-env", help="Show required environment variables"
    ),
) -> None:
    """List available server recipes."""
    categories = {}
    for name, recipe in SERVER_RECIPES.items():
        cat = recipe.get("category", "other")
        if category and cat != category:
            continue
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((name, recipe))

    if not categories:
        console.print(f"[yellow]No recipes found for category: {category}[/yellow]")
        return

    for cat, recipes in sorted(categories.items()):
        console.print(f"\n[bold cyan]{cat.upper()} SERVERS[/bold cyan]")

        table = Table(show_header=False, box=None)
        table.add_column("Name", style="green", width=20)
        table.add_column("Description", style="dim")

        for name, recipe in recipes:
            desc = recipe.get("description", "")
            if show_env and recipe.get("env_required"):
                desc += f" [yellow]({', '.join(recipe['env_required'])})[/yellow]"
            table.add_row(f"  {name}", desc)

        console.print(table)

    console.print(
        "\n[dim]Use: [cyan]mcp-agent server add recipe <name>[/cyan] to add a server[/dim]"
    )


@app.command("add")
def add(
    kind: str = typer.Argument(..., help="http|sse|stdio|npx|uvx|recipe|dxt|auto"),
    value: str = typer.Argument(..., help="URL, command, or recipe name"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Server name"),
    auth: Optional[str] = typer.Option(None, "--auth", help="Authorization token"),
    env: Optional[str] = typer.Option(
        None, "--env", "-e", help="Environment variables (KEY=value,...)"
    ),
    write: bool = typer.Option(
        True, "--write/--no-write", help="Persist to config file"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing server"
    ),
    extract_to: Optional[str] = typer.Option(
        None,
        "--extract-to",
        help="Extraction dir for .dxt (defaults to .mcp-agent/extensions/<name>)",
    ),
) -> None:
    """Add a server to configuration."""
    settings = get_settings()
    if settings.mcp is None:
        settings.mcp = MCPSettings()
    servers = settings.mcp.servers or {}

    # Parse environment variables
    env_dict = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_dict[k.strip()] = v.strip()

    entry = MCPServerSettings()

    if kind == "auto":
        # Auto-detect based on value
        if value.startswith("http://") or value.startswith("https://"):
            kind = "http"
        elif value in SERVER_RECIPES:
            kind = "recipe"
        elif "/" in value or "." in value:
            kind = "stdio"
        else:
            console.print("[yellow]Could not auto-detect server type[/yellow]")
            raise typer.Exit(1)

    if kind == "recipe":
        recipe = SERVER_RECIPES.get(value)
        if not recipe:
            console.print(f"[red]Unknown recipe: {value}[/red]")
            console.print(
                "[dim]Use [cyan]mcp-agent server recipes[/cyan] to see available recipes[/dim]"
            )
            raise typer.Exit(1)

        # Check for required environment variables
        if recipe.get("env_required"):
            missing = []
            import os

            for var in recipe["env_required"]:
                if not os.getenv(var) and var not in env_dict:
                    missing.append(var)

            if missing:
                console.print(
                    "[yellow]Warning: Required environment variables not set:[/yellow]"
                )
                for var in missing:
                    console.print(f"  • {var}")
                console.print(
                    "\n[dim]Add them to mcp_agent.secrets.yaml or set as environment variables[/dim]"
                )
                if not Confirm.ask("Continue anyway?", default=False):
                    raise typer.Exit(0)

        entry.transport = recipe["transport"]
        entry.command = recipe.get("command")
        entry.args = recipe.get("args", [])
        entry.env = {**recipe.get("env", {}), **env_dict}

        srv_name = name or value

        # Show what will be added
        console.print("\n[bold]Adding server from recipe:[/bold]")
        console.print(f"  Name: [cyan]{srv_name}[/cyan]")
        console.print(f"  Description: {recipe.get('description', 'N/A')}")
        console.print(f"  Command: {entry.command} {' '.join(entry.args)}")

    elif kind == "dxt":
        # Desktop Extension: zip archive or extracted directory with manifest.json
        from pathlib import Path as _Path
        import json as _json
        import zipfile

        dxt_path = _Path(value).expanduser()
        if not dxt_path.exists():
            console.print(f"[red]DXT not found: {dxt_path}[/red]")
            raise typer.Exit(1)

        # Determine extraction directory and server name
        default_name = name or dxt_path.stem
        base_extract_dir = (
            _Path(extract_to)
            if extract_to
            else (_Path.cwd() / ".mcp-agent" / "extensions" / default_name)
        )
        manifest_data = None
        manifest_dir = None

        try:
            if dxt_path.is_file() and dxt_path.suffix.lower() == ".dxt":
                base_extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(str(dxt_path), "r") as zf:
                    zf.extractall(base_extract_dir)
                manifest_dir = base_extract_dir
            else:
                # treat as directory containing manifest.json
                manifest_dir = dxt_path

            manifest_file = manifest_dir / "manifest.json"
            if not manifest_file.exists():
                console.print("[red]manifest.json not found in extension[/red]")
                raise typer.Exit(1)
            manifest_data = _json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[red]Failed to process DXT: {e}[/red]")
            raise typer.Exit(1)

        # Heuristics: look for stdio run specification
        # Support shapes: {"stdio": {"command": "...", "args": [...]}} or top-level "command"/"args"
        stdio_cfg = (
            manifest_data.get("stdio") if isinstance(manifest_data, dict) else None
        )
        cmd = None
        args = []
        env_vars = {}
        if isinstance(stdio_cfg, dict):
            cmd = stdio_cfg.get("command") or stdio_cfg.get("cmd")
            args = stdio_cfg.get("args") or []
            env_vars = stdio_cfg.get("env") or {}
        else:
            cmd = (
                manifest_data.get("command")
                if isinstance(manifest_data, dict)
                else None
            )
            args = (
                manifest_data.get("args") if isinstance(manifest_data, dict) else []
            ) or []
            env_vars = (
                manifest_data.get("env") if isinstance(manifest_data, dict) else {}
            ) or {}

        if not cmd:
            console.print("[red]DXT manifest missing stdio command[/red]")
            raise typer.Exit(1)

        entry.transport = "stdio"
        entry.command = cmd
        entry.args = args
        # Merge env from CLI
        entry.env = {**env_vars, **env_dict}

        srv_name = name or default_name
        console.print("\n[bold]Adding DXT server:[/bold]")
        console.print(f"  Name: [cyan]{srv_name}[/cyan]")
        console.print(f"  Extracted: {manifest_dir}")
        console.print(f"  Command: {cmd} {' '.join(args)}")

    elif kind in ("http", "sse"):
        entry.transport = kind
        entry.url = value
        if auth:
            entry.headers = {"Authorization": f"Bearer {auth}"}
        if env_dict:
            entry.env = env_dict
        srv_name = name or value.split("/")[-1].split("?")[0]

    elif kind in ("npx", "uvx"):
        # Convenience shortcuts
        entry.transport = "stdio"
        entry.command = kind
        entry.args = [value] if " " not in value else value.split()
        entry.env = env_dict
        srv_name = name or value.split("/")[-1]

    else:
        # stdio with full command
        entry.transport = "stdio"
        parts = value.split()
        entry.command = parts[0]
        entry.args = parts[1:] if len(parts) > 1 else []
        entry.env = env_dict
        srv_name = name or parts[0].split("/")[-1]

    # Check if server already exists
    if srv_name in servers and not force:
        console.print(f"[yellow]Server '{srv_name}' already exists[/yellow]")
        if not Confirm.ask("Overwrite?", default=False):
            raise typer.Exit(0)

    servers[srv_name] = entry

    if write:
        _persist_server_entry(srv_name, entry)
    else:
        console.print(
            f"[green]✅[/green] Added server '[cyan]{srv_name}[/cyan]' (not persisted)"
        )


@app.command("remove")
def remove_server(
    name: str = typer.Argument(..., help="Server name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove a server from configuration."""
    import yaml

    cfg_path, data = _load_config_yaml()

    if "mcp" not in data or "servers" not in data["mcp"]:
        console.print("[yellow]No servers configured[/yellow]")
        raise typer.Exit(1)

    servers = data["mcp"]["servers"]

    if name not in servers:
        console.print(f"[red]Server '{name}' not found[/red]")
        raise typer.Exit(1)

    if not force:
        server_info = servers[name]
        console.print("[bold]Server to remove:[/bold]")
        console.print(f"  Name: [cyan]{name}[/cyan]")
        console.print(f"  Transport: {server_info.get('transport', 'N/A')}")
        if not Confirm.ask("Remove this server?", default=False):
            raise typer.Exit(0)

    del servers[name]

    if not cfg_path:
        from pathlib import Path as _Path

        cfg_path = _Path("mcp_agent.config.yaml")

    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
    console.print(f"[green]✅[/green] Removed server '[cyan]{name}[/cyan]'")


@app.command("test")
def test(
    name: str = typer.Argument(..., help="Server name to test"),
    timeout: float = typer.Option(10.0, "--timeout", "-t", help="Connection timeout"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Test server connectivity and capabilities."""
    import asyncio
    from mcp_agent.app import MCPApp
    from mcp_agent.agents.agent import Agent

    async def _probe():
        app_obj = MCPApp(name="server-test")
        async with app_obj.run():
            console.print(f"[bold]Testing server: [cyan]{name}[/cyan][/bold]\n")

            try:
                agent = Agent(
                    name="probe", server_names=[name], context=app_obj.context
                )

                with console.status(f"Connecting to {name}..."):
                    async with agent:
                        # Get capabilities
                        caps = await agent.get_capabilities(server_name=name)

                        console.print("[green]✅ Connection successful![/green]\n")

                        # Display capabilities
                        if caps:
                            cap_list = []
                            if hasattr(caps, "tools") and caps.tools:
                                cap_list.append("tools")
                            if hasattr(caps, "resources") and caps.resources:
                                cap_list.append("resources")
                            if hasattr(caps, "prompts") and caps.prompts:
                                cap_list.append("prompts")

                            if cap_list:
                                console.print(
                                    f"[bold]Capabilities:[/bold] {', '.join(cap_list)}\n"
                                )

                        # List tools
                        tools = await agent.list_tools(server_name=name)
                        if tools and tools.tools:
                            console.print(f"[bold]Tools ({len(tools.tools)}):[/bold]")
                            if verbose:
                                for t in tools.tools:
                                    console.print(f"  • [green]{t.name}[/green]")
                                    if t.description:
                                        console.print(f"    {t.description[:80]}")
                            else:
                                # Show first 5 tools
                                for t in tools.tools[:5]:
                                    console.print(f"  • [green]{t.name}[/green]")
                                if len(tools.tools) > 5:
                                    console.print(
                                        f"  [dim]... and {len(tools.tools) - 5} more[/dim]"
                                    )

                        # List resources
                        try:
                            resources = await agent.list_resources(server_name=name)
                            if resources and resources.resources:
                                console.print(
                                    f"\n[bold]Resources ({len(resources.resources)}):[/bold]"
                                )
                                if verbose:
                                    for r in resources.resources:
                                        console.print(f"  • [blue]{r.uri}[/blue]")
                                        if hasattr(r, "description") and r.description:
                                            console.print(f"    {r.description[:80]}")
                                else:
                                    for r in resources.resources[:5]:
                                        console.print(f"  • [blue]{r.uri}[/blue]")
                                    if len(resources.resources) > 5:
                                        console.print(
                                            f"  [dim]... and {len(resources.resources) - 5} more[/dim]"
                                        )
                        except Exception:
                            pass  # Resources might not be supported

                        console.print(
                            f"\n[green bold]✅ Server '{name}' is working correctly![/green bold]",
                            end="\n\n",
                        )

            except asyncio.TimeoutError:
                console.print(f"[red]❌ Connection timeout ({timeout}s)[/red]")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]❌ Connection failed: {e}[/red]")
                if verbose:
                    import traceback

                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                raise typer.Exit(1)

        # Force complete shutdown of logging infrastructure for CLI commands
        await cleanup_context(shutdown_logger=True)

    try:
        asyncio.run(asyncio.wait_for(_probe(), timeout=timeout))
    except asyncio.TimeoutError:
        console.print(f"[red]❌ Test timeout ({timeout}s)[/red]")
        raise typer.Exit(1)
    except Exception:
        raise typer.Exit(1)


# Import subcommands
import_app = typer.Typer(help="Import server configs from various sources")


@import_app.command("claude")
def import_claude(
    show_only: bool = typer.Option(
        False, "--show-only", help="Show servers without importing"
    ),
) -> None:
    """Import servers from Claude Desktop configuration."""
    from pathlib import Path as _Path
    import platform

    # Claude Desktop config locations by platform
    if platform.system() == "Darwin":  # macOS
        config_paths = [
            _Path.home()
            / "Library/Application Support/Claude/claude_desktop_config.json",
        ]
    elif platform.system() == "Windows":
        config_paths = [
            _Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json",
        ]
    else:  # Linux
        config_paths = [
            _Path.home() / ".config/Claude/claude_desktop_config.json",
        ]

    found = False
    for config_path in config_paths:
        if config_path.exists():
            found = True
            try:
                config = json.loads(config_path.read_text())
                servers = config.get("mcpServers", {})

                if not servers:
                    console.print(
                        "[yellow]No servers found in Claude Desktop config[/yellow]"
                    )
                    return

                console.print(
                    f"[bold]Found {len(servers)} servers in Claude Desktop:[/bold]\n"
                )

                for name, server_config in servers.items():
                    console.print(f"  • [cyan]{name}[/cyan]")
                    if show_only:
                        console.print(
                            f"    Command: {server_config.get('command', 'N/A')}"
                        )
                        if server_config.get("args"):
                            console.print(
                                f"    Args: {' '.join(server_config['args'])}"
                            )

                if not show_only:
                    if Confirm.ask("\nImport these servers?", default=True):
                        for name, server_config in servers.items():
                            entry = MCPServerSettings()
                            entry.transport = "stdio"
                            entry.command = server_config.get("command", "")
                            entry.args = server_config.get("args", [])
                            entry.env = server_config.get("env", {})
                            _persist_server_entry(name, entry)
                        console.print(
                            f"\n[green]✅ Imported {len(servers)} servers[/green]"
                        )

            except Exception as e:
                console.print(f"[red]Error reading Claude config: {e}[/red]")

    if not found:
        console.print("[yellow]Claude Desktop configuration not found[/yellow]")
        console.print("[dim]Expected locations:[/dim]")
        for path in config_paths:
            console.print(f"  • {path}")


@import_app.command("cursor")
def import_cursor() -> None:
    """Import servers from Cursor configuration."""
    from pathlib import Path as _Path

    candidates = [
        _Path(".cursor/mcp.json").resolve(),
        _Path.home() / ".cursor/mcp.json",
    ]

    imported_any = False
    for p in candidates:
        if p.exists():
            try:
                console.print(f"[bold]Found Cursor config: {p}[/bold]")
                imported = import_servers_from_mcp_json(p)
                if imported:
                    console.print(f"Importing {len(imported)} servers...")
                    for name, cfg in imported.items():
                        _persist_server_entry(name, cfg)
                        imported_any = True
            except Exception as e:
                console.print(f"[red]Error importing from {p}: {e}[/red]")
                continue

    if imported_any:
        console.print("[green]✅ Successfully imported servers from Cursor[/green]")
    else:
        console.print("[yellow]No Cursor mcp.json found[/yellow]")
        console.print("[dim]Expected locations:[/dim]")
        for path in candidates:
            console.print(f"  • {path}")


@import_app.command("vscode")
def import_vscode() -> None:
    """Import servers from VSCode/Continue configuration."""
    from pathlib import Path as _Path

    candidates = [
        _Path(".vscode/mcp.json").resolve(),
        _Path.home() / ".vscode/mcp.json",
        _Path.cwd() / "mcp.json",
    ]

    imported_any = False
    for p in candidates:
        if p.exists():
            try:
                console.print(f"[bold]Found VSCode config: {p}[/bold]")
                imported = import_servers_from_mcp_json(p)
                if imported:
                    console.print(f"Importing {len(imported)} servers...")
                    for name, cfg in imported.items():
                        _persist_server_entry(name, cfg)
                        imported_any = True
            except Exception as e:
                console.print(f"[red]Error importing from {p}: {e}[/red]")
                continue

    if imported_any:
        console.print("[green]✅ Successfully imported servers from VSCode[/green]")
    else:
        console.print("[yellow]No VSCode mcp.json found[/yellow]")
        console.print("[dim]Expected locations:[/dim]")
        for path in candidates:
            console.print(f"  • {path}")


@import_app.command("mcp-json")
def import_mcp_json(path: str = typer.Argument(..., help="Path to mcp.json")) -> None:
    """Import servers from a generic mcp.json file."""
    from pathlib import Path as _Path

    p = _Path(path).expanduser()
    if not p.exists():
        console.print(f"[red]File not found: {p}[/red]")
        raise typer.Exit(1)
    try:
        servers = import_servers_from_mcp_json(p)
        if not servers:
            console.print("[yellow]No servers found in file[/yellow]")
            raise typer.Exit(1)
        for name, cfg in servers.items():
            _persist_server_entry(name, cfg)
        console.print(f"[green]✅ Imported {len(servers)} servers from {p}[/green]")
    except Exception as e:
        console.print(f"[red]Error importing from {p}: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("dxt")
def import_dxt(
    path: str = typer.Argument(
        ..., help="Path to .dxt or extracted manifest directory"
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Server name"),
    extract_to: Optional[str] = typer.Option(
        None,
        "--extract-to",
        help="Extraction dir for .dxt (defaults to .mcp-agent/extensions/<name>)",
    ),
) -> None:
    """Import a Desktop Extension (.dxt) by delegating to 'server add dxt'."""
    try:
        add(
            kind="dxt",
            value=path,
            name=name,
            write=True,
            force=False,
            extract_to=extract_to,
        )
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[red]Failed to import DXT: {e}[/red]")
        raise typer.Exit(1)


@import_app.command("smithery")
def import_smithery(
    url: str = typer.Argument(..., help="Smithery server URL"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Server name"),
) -> None:
    """Import a server from smithery.ai."""
    # Parse smithery URL to extract server info
    # Example: https://smithery.ai/server/mcp-server-fetch

    import re

    match = re.search(r"smithery\.ai/server/([^/]+)", url)
    if not match:
        console.print("[red]Invalid smithery URL[/red]")
        console.print(
            "[dim]Expected format: https://smithery.ai/server/<server-name>[/dim]"
        )
        raise typer.Exit(1)

    server_id = match.group(1)
    srv_name = name or server_id

    # Check if it's a known recipe
    if server_id in SERVER_RECIPES:
        console.print(f"[green]Found recipe for {server_id}[/green]")
        add(kind="recipe", value=server_id, name=srv_name, write=True)
    else:
        console.print(f"[yellow]Unknown smithery server: {server_id}[/yellow]")
        console.print("[dim]You may need to manually configure this server[/dim]")

        # Suggest common patterns
        if "npx" in url or "npm" in url:
            console.print(
                f"\n[dim]Try: mcp-agent server add npx @modelcontextprotocol/{server_id} --name {srv_name}[/dim]"
            )
        else:
            console.print(
                f"\n[dim]Try: mcp-agent server add uvx {server_id} --name {srv_name}[/dim]"
            )


@import_app.command("discover")
def discover_servers() -> None:
    """Discover and suggest servers from various sources."""
    from pathlib import Path as _Path
    import platform

    console.print("[bold cyan]🔍 Discovering MCP Servers[/bold cyan]\n")

    discoveries = []

    # Check for Claude Desktop
    if platform.system() == "Darwin":
        claude_path = (
            _Path.home()
            / "Library/Application Support/Claude/claude_desktop_config.json"
        )
        if claude_path.exists():
            discoveries.append(("Claude Desktop", "mcp-agent server import claude"))

    # Check for local mcp.json files
    local_configs = [
        (_Path(".cursor/mcp.json"), "Cursor", "mcp-agent server import cursor"),
        (_Path(".vscode/mcp.json"), "VSCode", "mcp-agent server import vscode"),
        (_Path("mcp.json"), "Local", "mcp-agent server import mcp-json mcp.json"),
    ]

    for path, name, cmd in local_configs:
        if path.exists():
            discoveries.append((name, cmd))

    # Check for common server commands
    import shutil

    available_commands = []

    if shutil.which("npx"):
        available_commands.append("npx (Node.js packages)")
    if shutil.which("uvx"):
        available_commands.append("uvx (Python packages)")
    if shutil.which("docker"):
        available_commands.append("docker")

    if discoveries:
        console.print("[bold]Found configurations:[/bold]")
        for source, cmd in discoveries:
            console.print(f"  • [green]{source}[/green]")
            console.print(f"    Import: [cyan]{cmd}[/cyan]")
        console.print()

    if available_commands:
        console.print("[bold]Available package managers:[/bold]")
        for cmd in available_commands:
            console.print(f"  • [green]{cmd}[/green]")
        console.print()

    # Suggest popular servers
    console.print("[bold]Popular servers to try:[/bold]")
    suggestions = [
        ("filesystem", "File system access"),
        ("fetch", "Web fetching"),
        ("github", "GitHub integration"),
        ("brave-search", "Web search"),
    ]

    for name, desc in suggestions:
        console.print(f"  • [cyan]{name}[/cyan] - {desc}")
        console.print(f"    Add: [dim]mcp-agent server add recipe {name}[/dim]")

    console.print(
        "\n[dim]View all recipes: [cyan]mcp-agent server recipes[/cyan][/dim]"
    )


app.add_typer(import_app, name="import")
