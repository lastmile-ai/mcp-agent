"""
Config command group: show, check, edit, builder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any
import os
import json

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.config import Settings, get_settings


app = typer.Typer(help="Configuration utilities")
console = Console()


def _find_config_file() -> Optional[Path]:
    return Settings.find_config()


def _find_secrets_file() -> Optional[Path]:
    return Settings.find_secrets()


def _load_template(template_name: str) -> str:
    """Load a template file from the data/templates directory."""
    try:
        from importlib import resources

        with (
            resources.files("mcp_agent.data.templates")
            .joinpath(template_name)
            .open() as file
        ):
            return file.read()
    except Exception as e:
        console.print(f"[red]Error loading template {template_name}: {e}[/red]")
        return ""


@app.command("show")
def show(
    secrets: bool = typer.Option(False, "--secrets", "-s", help="Show secrets file"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Explicit path"),
    raw: bool = typer.Option(
        False, "--raw", "-r", help="Show raw YAML without validation"
    ),
) -> None:
    """Display the current config or secrets file with YAML validation."""
    file_path = path
    if file_path is None:
        file_path = _find_secrets_file() if secrets else _find_config_file()

    if not file_path or not file_path.exists():
        typer.secho("Config file not found", fg=typer.colors.RED, err=True)
        console.print(
            "\n[dim]Hint: Run [cyan]mcp-agent config builder[/cyan] to create one[/dim]"
        )
        raise typer.Exit(2)

    try:
        text = file_path.read_text(encoding="utf-8")

        if raw:
            console.print(text)
            return

        # Parse and validate YAML
        parsed = yaml.safe_load(text)

        # Display file info
        console.print(
            Panel(
                f"[bold cyan]{file_path}[/bold cyan]\n"
                f"Size: {file_path.stat().st_size} bytes\n"
                f"Modified: {Path(file_path).stat().st_mtime}",
                title=f"[bold]{'Secrets' if secrets else 'Config'} File[/bold]",
                border_style="cyan",
            )
        )

        if parsed is None:
            console.print("\n[yellow]⚠️  File is empty[/yellow]")
        else:
            console.print("\n[green]✅ YAML syntax is valid[/green]")

            # Show structure summary
            console.print("\n[bold]Structure:[/bold]")
            for key in parsed.keys():
                if isinstance(parsed[key], dict):
                    console.print(f"  • {key}: {len(parsed[key])} items")
                else:
                    console.print(f"  • {key}: {type(parsed[key]).__name__}")

        # Show content with syntax highlighting
        console.print("\n[bold]Content:[/bold]")
        from rich.syntax import Syntax

        syntax = Syntax(text, "yaml", theme="monokai", line_numbers=True)
        console.print(syntax)

    except yaml.YAMLError as e:
        console.print(f"[red]❌ YAML syntax error: {e}[/red]")
        console.print("\n[yellow]Raw content:[/yellow]")
        console.print(text)
        raise typer.Exit(5)
    except Exception as e:
        typer.secho(f"Error reading file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(5)


@app.command("check")
def check(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
) -> None:
    """Check and summarize configuration status."""
    cfg = _find_config_file()
    sec = _find_secrets_file()

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan", width=20)
    table.add_column("Value")

    # File status
    table.add_row("Config file", str(cfg) if cfg else "[red]Not found[/red]")
    table.add_row("Secrets file", str(sec) if sec else "[yellow]Not found[/yellow]")

    if not cfg:
        console.print(
            Panel(table, title="[bold]Configuration Status[/bold]", border_style="red")
        )
        console.print(
            "\n[dim]Run [cyan]mcp-agent config builder[/cyan] to create configuration[/dim]"
        )
        raise typer.Exit(1)

    # Load and check settings
    try:
        settings = get_settings()

        # Basic configuration
        table.add_row("", "")  # Separator
        table.add_row("[bold]Engine[/bold]", "")
        table.add_row("Execution", settings.execution_engine or "asyncio")

        # Logger configuration
        if settings.logger:
            table.add_row("", "")
            table.add_row("[bold]Logger[/bold]", "")
            table.add_row("Type", settings.logger.type or "none")
            table.add_row("Level", settings.logger.level or "info")
            if settings.logger.type == "file":
                table.add_row(
                    "Path",
                    str(
                        settings.logger.path_settings.path_pattern
                        if settings.logger.path_settings
                        else "Not set"
                    ),
                )

        # OTEL configuration
        if settings.otel and settings.otel.enabled:
            table.add_row("", "")
            table.add_row("[bold]OpenTelemetry[/bold]", "")
            table.add_row("Enabled", "[green]Yes[/green]")
            table.add_row("Sample rate", str(settings.otel.sample_rate))
            if settings.otel.exporters:
                table.add_row(
                    "Exporters", ", ".join(str(e) for e in settings.otel.exporters)
                )

        # MCP servers
        table.add_row("", "")
        table.add_row("[bold]MCP Servers[/bold]", "")
        if settings.mcp and settings.mcp.servers:
            servers = list(settings.mcp.servers.keys())
            table.add_row("Count", str(len(servers)))
            if verbose:
                for name in servers[:5]:
                    server = settings.mcp.servers[name]
                    status = "✅" if server.transport == "stdio" else "🌐"
                    table.add_row(f"  {status} {name}", server.transport)
                if len(servers) > 5:
                    table.add_row("  ...", f"and {len(servers) - 5} more")
            else:
                table.add_row(
                    "Names",
                    ", ".join(servers[:3]) + ("..." if len(servers) > 3 else ""),
                )
        else:
            table.add_row("Count", "[yellow]0[/yellow]")

        # Provider status
        table.add_row("", "")
        table.add_row("[bold]Providers[/bold]", "")

        providers = [
            ("OpenAI", settings.openai, "api_key"),
            ("Anthropic", settings.anthropic, "api_key"),
            ("Google", settings.google, "api_key"),
            ("Azure", settings.azure, "api_key"),
        ]

        configured = []
        for name, obj, field in providers:
            if obj and getattr(obj, field, None):
                configured.append(name)
            elif os.getenv(f"{name.upper()}_API_KEY"):
                configured.append(f"{name} (env)")

        if configured:
            table.add_row("Configured", ", ".join(configured))
        else:
            table.add_row("Configured", "[yellow]None[/yellow]")

        # Show panel with status
        status_color = "green" if configured else "yellow"
        console.print(
            Panel(
                table,
                title="[bold]Configuration Status[/bold]",
                border_style=status_color,
            )
        )

        # Warnings and suggestions
        warnings = []

        if not sec or not sec.exists():
            warnings.append(
                "No secrets file found - API keys should be in environment variables"
            )

        if not configured:
            warnings.append("No AI providers configured - add API keys to use agents")

        if settings.mcp and not settings.mcp.servers:
            warnings.append("No MCP servers configured - agents won't have tool access")

        if warnings:
            console.print("\n[yellow]⚠️  Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"  • {warning}")

        if verbose:
            console.print(
                "\n[dim]Run [cyan]mcp-agent doctor[/cyan] for detailed diagnostics[/dim]"
            )

    except Exception as e:
        table.add_row("", "")
        table.add_row("Error", f"[red]{e}[/red]")
        console.print(
            Panel(table, title="[bold]Configuration Status[/bold]", border_style="red")
        )
        raise typer.Exit(5)


@app.command("edit")
def edit(
    secrets: bool = typer.Option(False, "--secrets", "-s", help="Edit secrets file"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor to use"),
) -> None:
    """Open config or secrets in an editor."""
    target = _find_secrets_file() if secrets else _find_config_file()

    if not target:
        console.print(f"[red]No {'secrets' if secrets else 'config'} file found[/red]")
        if Confirm.ask("Create one now?", default=True):
            builder()
            return
        raise typer.Exit(2)

    import subprocess

    # Determine editor
    if editor:
        editors = [editor]
    else:
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        editors = [editor] if editor else []
        editors += ["code --wait", "nano", "vim", "vi", "emacs"]

    # Try each editor
    for cmd in editors:
        if not cmd:
            continue
        try:
            # Inform user about validation behavior
            console.print(f"\n[cyan]Opening {target.name} in editor...[/cyan]")
            console.print("[dim]Save and close the editor to continue.[/dim]\n")
            # Handle editors with arguments
            if " " in cmd:
                parts = cmd.split()
                subprocess.run(parts + [str(target)], check=True)
            else:
                subprocess.run([cmd, str(target)], check=True)

            # Validate after editing
            console.print("\n[bold]Validating edited file...[/bold]")
            try:
                yaml.safe_load(target.read_text())
                console.print("[green]✅ File is valid YAML[/green]")
            except yaml.YAMLError as e:
                console.print(f"[red]⚠️  YAML syntax error: {e}[/red]")
            return

        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    # If all editors fail, show the path
    console.print("[yellow]No editor found. File location:[/yellow]")
    console.print(str(target))


@app.command("builder")
def builder(
    expert: bool = typer.Option(False, "--expert", help="Expert mode with all options"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Start from template"
    ),
) -> None:
    """Interactive configuration builder."""
    console.print("\n[bold cyan]🔧 MCP-Agent Configuration Builder[/bold cyan]\n")

    # Check existing files
    existing_config = _find_config_file()
    existing_secrets = _find_secrets_file()

    if existing_config and existing_config.exists():
        console.print(f"[yellow]⚠️  Config file exists: {existing_config}[/yellow]")
        if not Confirm.ask("Overwrite?", default=False):
            raise typer.Exit(0)

    # Initialize config structure
    config: Dict[str, Any] = {}
    secrets: Dict[str, Any] = {}

    # Load template if specified
    if template:
        template_map = {
            "basic": "mcp_agent.config.yaml",
            "claude": "config_claude.yaml",
            "server": "config_server.yaml",
        }

        template_file = template_map.get(template, template)
        template_content = _load_template(template_file)

        if template_content:
            try:
                config = yaml.safe_load(template_content) or {}
                console.print(f"[green]Loaded template: {template}[/green]")
            except Exception as e:
                console.print(f"[red]Failed to load template: {e}[/red]")

    # Basic configuration
    console.print("\n[bold]Basic Configuration[/bold]")

    config["execution_engine"] = Prompt.ask(
        "Execution engine",
        default=config.get("execution_engine", "asyncio"),
        choices=["asyncio", "temporal"],
    )

    # Logger configuration
    console.print("\n[bold]Logger Configuration[/bold]")

    logger_type = Prompt.ask(
        "Logger type", default="console", choices=["none", "console", "file", "http"]
    )

    config.setdefault("logger", {})
    config["logger"]["type"] = logger_type

    if logger_type != "none":
        config["logger"]["level"] = Prompt.ask(
            "Log level", default="info", choices=["debug", "info", "warning", "error"]
        )

        if logger_type == "console":
            config["logger"]["transports"] = ["console"]
        elif logger_type == "file":
            config["logger"]["transports"] = ["file"]
            config["logger"]["path_settings"] = {
                "path_pattern": Prompt.ask(
                    "Log file pattern", default="logs/mcp-agent-{unique_id}.jsonl"
                ),
                "unique_id": Prompt.ask(
                    "Unique ID type",
                    default="timestamp",
                    choices=["timestamp", "session_id"],
                ),
            }

    # OpenTelemetry (expert mode)
    if expert:
        console.print("\n[bold]OpenTelemetry Configuration[/bold]")

        if Confirm.ask("Enable OpenTelemetry?", default=False):
            config.setdefault("otel", {})
            config["otel"]["enabled"] = True
            config["otel"]["service_name"] = Prompt.ask(
                "Service name", default="mcp-agent"
            )
            config["otel"]["endpoint"] = Prompt.ask(
                "OTLP endpoint", default="http://localhost:4317"
            )
            config["otel"]["sample_rate"] = float(
                Prompt.ask("Sample rate (0.0-1.0)", default="1.0")
            )

    # MCP Servers
    console.print("\n[bold]MCP Server Configuration[/bold]")

    config.setdefault("mcp", {})
    config["mcp"].setdefault("servers", {})

    # Quick server setup
    if Confirm.ask("Add filesystem server?", default=True):
        config["mcp"]["servers"]["filesystem"] = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        }

    if Confirm.ask("Add web fetch server?", default=True):
        config["mcp"]["servers"]["fetch"] = {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-fetch"],
        }

    # Additional servers
    if Confirm.ask("Add more servers?", default=False):
        # Show available recipes
        from mcp_agent.cli.commands.server import SERVER_RECIPES

        categories = {}
        for name, recipe in SERVER_RECIPES.items():
            cat = recipe.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(name)

        console.print("\n[bold]Available server recipes:[/bold]")
        for cat, names in sorted(categories.items()):
            console.print(f"  [cyan]{cat}:[/cyan] {', '.join(names[:5])}")

        while True:
            server_name = Prompt.ask("\nServer recipe name (or 'done')")
            if server_name.lower() == "done":
                break

            if server_name in SERVER_RECIPES:
                recipe = SERVER_RECIPES[server_name]
                config["mcp"]["servers"][server_name] = {
                    "transport": recipe["transport"],
                    "command": recipe.get("command"),
                    "args": recipe.get("args", []),
                }
                console.print(f"[green]Added: {server_name}[/green]")

                # Check for required env vars
                if recipe.get("env_required"):
                    console.print(
                        f"[yellow]Note: Requires {', '.join(recipe['env_required'])}[/yellow]"
                    )
            else:
                console.print(f"[red]Unknown recipe: {server_name}[/red]")

    # Provider configuration
    console.print("\n[bold]AI Provider Configuration[/bold]")

    providers = [
        ("openai", "OpenAI", "gpt-4o-mini"),
        ("anthropic", "Anthropic", "claude-3-5-sonnet-20241022"),
        ("google", "Google", "gemini-1.5-pro"),
    ]

    for key, name, default_model in providers:
        if Confirm.ask(f"Configure {name}?", default=key in ["openai", "anthropic"]):
            config.setdefault(key, {})
            config[key]["default_model"] = Prompt.ask(
                f"{name} default model", default=default_model
            )

            # Ask for API key for secrets file
            if Confirm.ask(f"Add {name} API key to secrets?", default=True):
                api_key = Prompt.ask(f"{name} API key", password=True)
                if api_key and api_key != "skip":
                    secrets.setdefault(key, {})
                    secrets[key]["api_key"] = api_key

    # Schema reference
    config["$schema"] = (
        "https://raw.githubusercontent.com/lastmile-ai/mcp-agent/refs/heads/main/schema/mcp-agent.config.schema.json"
    )

    # Write config file
    config_path = existing_config or Path.cwd() / "mcp_agent.config.yaml"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Writing configuration files...", total=None)

        try:
            # Write config
            config_yaml = yaml.safe_dump(
                config, sort_keys=False, default_flow_style=False
            )
            config_path.write_text(config_yaml, encoding="utf-8")
            console.print(f"[green]✅ Created:[/green] {config_path}")

            # Write secrets if any
            if secrets:
                secrets_path = existing_secrets or Path.cwd() / "mcp_agent.secrets.yaml"

                # Load template and merge
                template_secrets = _load_template("mcp_agent.secrets.yaml")
                if template_secrets:
                    base_secrets = yaml.safe_load(template_secrets) or {}
                    # Merge user secrets into template
                    for key, value in secrets.items():
                        if key in base_secrets and isinstance(base_secrets[key], dict):
                            base_secrets[key].update(value)
                        else:
                            base_secrets[key] = value
                    secrets = base_secrets

                secrets_yaml = yaml.safe_dump(
                    secrets, sort_keys=False, default_flow_style=False
                )
                secrets_path.write_text(secrets_yaml, encoding="utf-8")
                console.print(f"[green]✅ Created:[/green] {secrets_path}")

                # Set secure permissions
                try:
                    import stat

                    os.chmod(secrets_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
                    console.print("[dim]Set secure permissions on secrets file[/dim]")
                except Exception:
                    pass

            # Create .gitignore if needed
            gitignore = Path.cwd() / ".gitignore"
            if (
                not gitignore.exists()
                or "mcp_agent.secrets.yaml" not in gitignore.read_text()
            ):
                if Confirm.ask("Add secrets to .gitignore?", default=True):
                    with open(gitignore, "a") as f:
                        f.write(
                            "\n# MCP-Agent\nmcp_agent.secrets.yaml\n*.secrets.yaml\n"
                        )
                    console.print("[green]✅ Updated .gitignore[/green]")

        except Exception as e:
            console.print(f"[red]Error writing files: {e}[/red]")
            raise typer.Exit(5)

    # Show summary
    console.print("\n[bold green]✅ Configuration complete![/bold green]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    table.add_row("Config file", str(config_path))
    table.add_row("MCP servers", str(len(config.get("mcp", {}).get("servers", {}))))
    table.add_row(
        "Providers",
        ", ".join(k for k in ["openai", "anthropic", "google"] if k in config),
    )

    console.print(Panel(table, title="[bold]Summary[/bold]", border_style="green"))

    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Review configuration: [cyan]mcp-agent config show[/cyan]")
    console.print("2. Test configuration: [cyan]mcp-agent doctor[/cyan]")
    console.print("3. Test servers: [cyan]mcp-agent server test <name>[/cyan]")
    console.print("4. Start chatting: [cyan]mcp-agent chat[/cyan]")


@app.command("validate")
def validate(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Config file path"
    ),
    secrets_file: Optional[Path] = typer.Option(
        None, "--secrets", "-s", help="Secrets file path"
    ),
    schema: Optional[str] = typer.Option(None, "--schema", help="Schema URL or path"),
) -> None:
    """Validate configuration files against schema."""
    config_path = config_file or _find_config_file()
    secrets_path = secrets_file or _find_secrets_file()

    if not config_path or not config_path.exists():
        console.print("[red]Config file not found[/red]")
        raise typer.Exit(1)

    console.print("[bold]Validating configuration files...[/bold]\n")

    errors = []
    warnings = []

    # Validate YAML syntax
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        console.print("[green]✅[/green] Config YAML syntax valid")
    except yaml.YAMLError as e:
        errors.append(f"Config YAML error: {e}")
        config = None

    if secrets_path and secrets_path.exists():
        try:
            with open(secrets_path) as f:
                yaml.safe_load(f)
            console.print("[green]✅[/green] Secrets YAML syntax valid")
        except yaml.YAMLError as e:
            errors.append(f"Secrets YAML error: {e}")
    else:
        warnings.append("No secrets file found")

    # Validate against schema if available
    if schema:
        try:
            import jsonschema
            import requests

            # Load schema
            if schema.startswith("http"):
                response = requests.get(schema)
                schema_data = response.json()
            else:
                with open(schema) as f:
                    schema_data = json.load(f)

            # Validate
            jsonschema.validate(config, schema_data)
            console.print("[green]✅[/green] Config validates against schema")

        except ImportError:
            warnings.append("jsonschema not installed - skipping schema validation")
        except Exception as e:
            errors.append(f"Schema validation error: {e}")

    # Validate settings can be loaded
    try:
        settings = get_settings()
        console.print("[green]✅[/green] Settings load successfully")

        # Check for common issues
        if settings.mcp and settings.mcp.servers:
            for name, server in settings.mcp.servers.items():
                if server.transport == "stdio" and not server.command:
                    warnings.append(f"Server '{name}' missing command")
                elif server.transport in ["http", "sse"] and not server.url:
                    warnings.append(f"Server '{name}' missing URL")

    except Exception as e:
        errors.append(f"Settings load error: {e}")

    # Display results
    console.print()

    if errors:
        console.print("[bold red]Errors:[/bold red]")
        for error in errors:
            console.print(f"  ❌ {error}")

    if warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in warnings:
            console.print(f"  ⚠️  {warning}")

    if not errors:
        console.print("\n[bold green]✅ Configuration is valid![/bold green]")
    else:
        raise typer.Exit(1)
