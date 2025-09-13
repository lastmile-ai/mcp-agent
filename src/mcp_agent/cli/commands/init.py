"""
Project scaffolding: mcp-agent init (scaffold minimal version).
"""

from __future__ import annotations

from pathlib import Path
from importlib import resources

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(help="Scaffold a new mcp-agent project")
console = Console()


def _load_template(template_name: str) -> str:
    """Load a template file from the data/templates directory."""
    try:
        with (
            resources.files("mcp_agent.data.templates")
            .joinpath(template_name)
            .open() as file
        ):
            return file.read()
    except Exception as e:
        console.print(f"[red]Error loading template {template_name}: {e}[/red]")
        return ""


def _write(path: Path, content: str, force: bool) -> bool:
    """Write content to a file with optional overwrite confirmation."""
    if path.exists() and not force:
        if not Confirm.ask(f"{path} exists. Overwrite?", default=False):
            return False

    try:
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]Created[/green] {path}")
        return True
    except Exception as e:
        console.print(f"[red]Error writing {path}: {e}[/red]")
        return False


@app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    dir: Path = typer.Option(Path("."), "--dir", "-d", help="Target directory"),
    template: str = typer.Option("basic", "--template", "-t", help="Template to use"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
    no_gitignore: bool = typer.Option(
        False, "--no-gitignore", help="Skip creating .gitignore"
    ),
    list_templates: bool = typer.Option(
        False, "--list", "-l", help="List available templates"
    ),
) -> None:
    """Initialize a new MCP-Agent project with configuration and example files."""

    # Available templates with descriptions
    templates = {
        "basic": "Simple agent with filesystem and fetch capabilities",
        "server": "MCP server with workflow and parallel agents",
        "token": "Token counting example with monitoring",
        "factory": "Agent factory with router-based selection",
        "minimal": "Minimal configuration files only",
    }

    if list_templates:
        console.print("\n[bold]Available Templates:[/bold]\n")
        table = Table(show_header=True, header_style="cyan")
        table.add_column("Template", style="green")
        table.add_column("Description")

        for name, desc in templates.items():
            table.add_row(name, desc)

        console.print(table)
        console.print("\n[dim]Use: mcp-agent init --template <name>[/dim]")
        return

    if ctx.invoked_subcommand:
        return

    # Validate template
    if template not in templates:
        console.print(f"[red]Unknown template: {template}[/red]")
        console.print(f"Available templates: {', '.join(templates.keys())}")
        console.print("[dim]Use --list to see template descriptions[/dim]")
        raise typer.Exit(1)

    dir = dir.resolve()
    dir.mkdir(parents=True, exist_ok=True)

    console.print("\n[bold]Initializing MCP-Agent project[/bold]")
    console.print(f"Directory: [cyan]{dir}[/cyan]")
    console.print(f"Template: [cyan]{template}[/cyan] - {templates[template]}\n")

    files_created = []
    entry_script_name: str | None = None

    # Always create config files
    config_path = dir / "mcp_agent.config.yaml"
    config_content = _load_template("mcp_agent.config.yaml")
    if config_content and _write(config_path, config_content, force):
        files_created.append("mcp_agent.config.yaml")

    # Create secrets file
    secrets_path = dir / "mcp_agent.secrets.yaml"
    secrets_content = _load_template("secrets.yaml")
    if secrets_content and _write(secrets_path, secrets_content, force):
        files_created.append("mcp_agent.secrets.yaml")

    # Create gitignore
    if not no_gitignore:
        gitignore_path = dir / ".gitignore"
        gitignore_content = _load_template("gitignore.template")
        if gitignore_content and _write(gitignore_path, gitignore_content, force):
            files_created.append(".gitignore")

    # Create template-specific files
    if template == "basic":
        # Determine entry script name and handle existing files
        script_name = "main.py"
        script_path = dir / script_name
        agent_content = _load_template("basic_agent.py")

        if agent_content:
            write_force_flag = force
            if script_path.exists() and not force:
                if Confirm.ask(f"{script_path} exists. Overwrite?", default=False):
                    write_force_flag = True
                else:
                    # Ask for an alternate filename and ensure it ends with .py
                    alt_name = Prompt.ask(
                        "Enter a filename to save the agent", default="agent.py"
                    )
                    if not alt_name.endswith(".py"):
                        alt_name += ".py"
                    script_name = alt_name
                    script_path = dir / script_name
                    # keep write_force_flag as-is to allow overwrite prompt if needed

            if _write(script_path, agent_content, write_force_flag):
                files_created.append(script_name)
                entry_script_name = script_name
                # Make executable
                try:
                    script_path.chmod(script_path.stat().st_mode | 0o111)
                except Exception:
                    pass

    elif template == "server":
        server_path = dir / "server.py"
        server_content = _load_template("basic_agent_server.py")
        if server_content and _write(server_path, server_content, force):
            files_created.append("server.py")
            # Make executable
            try:
                server_path.chmod(server_path.stat().st_mode | 0o111)
            except Exception:
                pass

    elif template == "token":
        token_path = dir / "token_example.py"
        token_content = _load_template("token_counter.py")
        if token_content and _write(token_path, token_content, force):
            files_created.append("token_example.py")
            # Make executable
            try:
                token_path.chmod(token_path.stat().st_mode | 0o111)
            except Exception:
                pass

    elif template == "factory":
        factory_path = dir / "factory.py"
        factory_content = _load_template("agent_factory.py")
        if factory_content and _write(factory_path, factory_content, force):
            files_created.append("factory.py")
            # Make executable
            try:
                factory_path.chmod(factory_path.stat().st_mode | 0o111)
            except Exception:
                pass

        # Also create agents.yaml for factory template
        agents_path = dir / "agents.yaml"
        agents_content = _load_template("agents.yaml")
        if agents_content and _write(agents_path, agents_content, force):
            files_created.append("agents.yaml")

    # Display results
    if files_created:
        console.print("\n[green]✅ Successfully initialized project![/green]")
        console.print(f"Created {len(files_created)} file(s)\n")

        # Template-specific next steps
        console.print("[bold]Next steps:[/bold]")
        console.print("1. Add your API keys to [cyan]mcp_agent.secrets.yaml[/cyan]")
        console.print(
            "   Or set environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY"
        )
        console.print("2. Review and customize [cyan]mcp_agent.config.yaml[/cyan]")

        if template == "basic":
            run_file = entry_script_name or "main.py"
            console.print(f"3. Run your agent: [cyan]uv run {run_file}[/cyan]")
            console.print(
                f"   Or use: [cyan]mcp-agent dev start --script {run_file}[/cyan]"
            )
            console.print(
                f"   Or serve: [cyan]mcp-agent dev serve --script {run_file}[/cyan]"
            )
            console.print("   Or chat: [cyan]mcp-agent dev chat[/cyan]")
            console.print(
                "4. Edit config: [cyan]mcp-agent config edit[/cyan] (then rerun)"
            )
        elif template == "server":
            console.print("3. Run the server: [cyan]uv run server.py[/cyan]")
            console.print(
                "   Or serve: [cyan]mcp-agent dev serve --script server.py[/cyan]"
            )
        elif template == "token":
            console.print("3. Run the example: [cyan]uv run token_example.py[/cyan]")
            console.print("   Watch token usage in real-time!")
        elif template == "factory":
            console.print("3. Customize agents in [cyan]agents.yaml[/cyan]")
            console.print("4. Run the factory: [cyan]uv run factory.py[/cyan]")
        elif template == "minimal":
            console.print("3. Create your agent script")
            console.print("   See examples: [cyan]mcp-agent quickstart[/cyan]")

        console.print(
            "\n[dim]Run [cyan]mcp-agent doctor[/cyan] to check your configuration[/dim]"
        )
        console.print(
            "[dim]Run [cyan]mcp-agent init --list[/cyan] to see all available templates[/dim]"
        )
    else:
        console.print("\n[yellow]No files were created[/yellow]")


@app.command()
def interactive(
    dir: Path = typer.Option(Path("."), "--dir", "-d", help="Target directory"),
) -> None:
    """Interactive project initialization with prompts."""
    console.print("\n[bold cyan]🚀 MCP-Agent Interactive Setup[/bold cyan]\n")

    # Project name
    project_name = Prompt.ask("Project name", default=dir.name)

    # Template selection
    templates = {
        "1": ("basic", "Simple agent with filesystem and fetch"),
        "2": ("server", "MCP server with workflows"),
        "3": ("token", "Token counting with monitoring"),
        "4": ("factory", "Agent factory with routing"),
        "5": ("minimal", "Config files only"),
    }

    console.print("\n[bold]Choose a template:[/bold]")
    for key, (name, desc) in templates.items():
        console.print(f"  {key}. [green]{name}[/green] - {desc}")

    choice = Prompt.ask("\nTemplate", choices=list(templates.keys()), default="1")
    template_name, _ = templates[choice]

    # Provider selection
    console.print("\n[bold]Select AI providers to configure:[/bold]")
    providers = []

    if Confirm.ask("Configure OpenAI?", default=True):
        providers.append("openai")

    if Confirm.ask("Configure Anthropic?", default=True):
        providers.append("anthropic")

    if Confirm.ask("Configure Google?", default=False):
        providers.append("google")

    # MCP servers
    console.print("\n[bold]Select MCP servers to enable:[/bold]")
    servers = []

    if Confirm.ask("Enable filesystem access?", default=True):
        servers.append("filesystem")

    if Confirm.ask("Enable web fetch?", default=True):
        servers.append("fetch")

    if Confirm.ask("Enable GitHub integration?", default=False):
        servers.append("github")

    # Create project
    console.print(f"\n[bold]Creating project '{project_name}'...[/bold]")

    # Use the main init function with selected options
    init(
        ctx=typer.Context(),
        dir=dir,
        template=template_name,
        force=False,
        no_gitignore=False,
        list_templates=False,
    )

    # Additional configuration hints
    if "github" in servers:
        console.print(
            "\n[yellow]Note:[/yellow] GitHub server requires GITHUB_PERSONAL_ACCESS_TOKEN"
        )
        console.print("Add it to mcp_agent.secrets.yaml or set as environment variable")

    console.print("\n[green bold]✨ Project setup complete![/green bold]")
