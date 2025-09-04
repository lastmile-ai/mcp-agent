"""
Project scaffolding: mcp-agent init (scaffold minimal version).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm


app = typer.Typer(help="Scaffold a new mcp-agent project")
console = Console()


DEFAULT_CONFIG = """# mcp-agent configuration
mcp:
  servers: {}
logger:
  level: info
  type: console
"""

DEFAULT_SECRETS = """# mcp-agent secrets (do not commit)
openai:
  api_key: ""
anthropic:
  api_key: ""
"""

DEFAULT_AGENT = (
    """from mcp_agent.app import MCPApp

app = MCPApp(name="my_agent")

if __name__ == "__main__":
    import asyncio

    async def main():
        async with app.run():
            pass

    asyncio.run(main())
"""
)


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        if not Confirm.ask(f"{path} exists. Overwrite?", default=False):
            return
    path.write_text(content, encoding="utf-8")
    console.print(f"[green]Created[/green] {path}")


@app.callback(invoke_without_command=True)
def init(
    dir: Path = typer.Option(Path("."), "--dir", "-d", help="Target directory"),
    template: str = typer.Option("basic", "--template", help="Template name"),
    force: bool = typer.Option(False, "--force", "-f"),
    no_gitignore: bool = typer.Option(False, "--no-gitignore"),
) -> None:
    """Create config, secrets, and an example agent.py."""
    dir = dir.resolve()
    dir.mkdir(parents=True, exist_ok=True)

    _write(dir / "mcp_agent.config.yaml", DEFAULT_CONFIG, force)
    _write(dir / "mcp_agent.secrets.yaml", DEFAULT_SECRETS, force)
    _write(dir / "agent.py", DEFAULT_AGENT, force)
    if not no_gitignore:
        _write(dir / ".gitignore", "mcp_agent.secrets.yaml\n", force)

    console.print("\n[bold]Next:[/bold] uv run agent.py")


