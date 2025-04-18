# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "rich",
#     "typer",
# ]
# ///
"""
Run a specific example from the MCP Agent examples/ directory.
"""

import os
import shutil
import subprocess
import tempfile

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Manage MCP Agent examples")
console = Console()


def create_venv(example_dir: Path) -> Path:
    """Create a virtual environment if it doesn't exist."""
    venv_dir = example_dir / ".venv"
    if not venv_dir.exists():
        console.print(f"Creating virtual environment in [cyan]{venv_dir}[/]")
        subprocess.run(["uv", "venv", str(venv_dir)], check=True)
        # venv.create(venv_dir, with_pip=True)
    return venv_dir


def clean_venv(example_dir: Path) -> None:
    """Remove the virtual environment if it exists."""
    venv_dir = example_dir / ".venv"
    if venv_dir.exists():
        console.print(f"Removing virtual environment in [cyan]{venv_dir}[/]")
        shutil.rmtree(venv_dir)


def get_python_path(venv_dir: Path) -> Path:
    """Get the python executable path for the virtual environment."""
    # Run the example using the venv's Python
    python_path = (venv_dir / "bin" / "python").resolve()
    if not python_path.exists():
        python_path = (venv_dir / "Scripts" / "python").resolve()  # Windows path

    return python_path


def get_site_packages(venv_dir: Path, python_path: Path) -> Path:
    """Get the site-packages directory for the virtual environment."""
    # Construct site-packages path based on platform
    if (venv_dir / "lib").exists():  # Unix-like
        # Get Python version (e.g., "3.10")
        result = subprocess.run(
            [
                str(python_path),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        python_version = result.stdout.strip()
        return venv_dir / "lib" / f"python{python_version}" / "site-packages"
    else:  # Windows
        return venv_dir / "Lib" / "site-packages"


def create_requirements_file(
    example_dir: Path, use_local: bool, version: str | None
) -> Path:
    """Create a temporary requirements file with the correct mcp-agent source."""
    temp_req = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")

    with open(file=example_dir / "requirements.txt", mode="r", encoding="utf-8") as f:
        requirements = f.readlines()

    with open(file=temp_req.name, mode="w", encoding="utf-8") as f:
        # TODO: saqadri - consider just copying the original requirements file
        # f.writelines(requirements)
        for req in requirements:
            if not (
                req.strip().startswith("-e") or req.strip().startswith("mcp-agent")
            ):
                f.write(req)

        f.write("\n")

        if use_local:
            # Add the local source
            f.write("-e ../../\n")
            # f.write("mcp-agent @ file://../../\n")
        else:
            # Add the PyPI version
            version_str = f"=={version}" if version else ""
            f.write(f"mcp-agent{version_str}\n")

    return Path(temp_req.name)


@app.command(name="list")
def list_examples():
    """List all available examples."""
    examples_dir = Path("examples")
    if not examples_dir.exists():
        console.print("[red]No examples directory found[/]")
        raise typer.Exit(1)

    # Get top-level categories
    categories = [
        d for d in examples_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not categories:
        console.print("No example categories found")
        return

    console.print("\n[bold]Available example categories:[/]")
    for category in categories:
        console.print(f"\n[bold cyan]{category.name}[/]")
        
        # List examples in this category
        examples = [
            d for d in category.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]
        
        if not examples:
            console.print("  No examples in this category")
            continue
            
        for example in examples:
            example_readme = example / "README.md"
            description = ""
            if example_readme.exists():
                with open(file=example_readme, mode="r", encoding="utf-8") as f:
                    # Get first line of README as description
                    description = f.readline().strip("#").strip()

            console.print(f"  • [cyan]{example.name}[/] - {description}")


@app.command()
def run(
    example_path: str = typer.Argument(..., help="Path to the example (e.g., 'basic/mcp_basic_agent')"),
    use_local: bool = typer.Option(
        True, "--local", "-l", help="Use local version of mcp-agent"
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Specific version to install from PyPI"
    ),
    clean: bool = typer.Option(
        False, "--clean", "-c", help="Create a fresh virtual environment"
    ),
    debug: bool = typer.Option(False, "--debug", "-d", help="Print debug information"),
):
    """Run a specific example."""
    examples_dir = Path("examples").resolve()
    project_root = Path(__file__).resolve().parent.parent
    
    # Split path into category and example name
    parts = example_path.replace("\\", "/").split("/")
    if len(parts) != 2:
        console.print(f"[red]Invalid example path format: '{example_path}'. Use 'category/example_name'[/]")
        raise typer.Exit(1)
        
    category, example_name = parts
    example_dir = (examples_dir / category / example_name).resolve()
    
    if not example_dir.exists():
        console.print(f"[red]Example '{example_name}' not found in category '{category}'[/]")
        raise typer.Exit(1)

    # Clean if requested
    if clean:
        clean_venv(example_dir)

    # with console.status(f"Setting up example: {example_name}") as status:
    venv_dir = create_venv(example_dir)
    temp_req = create_requirements_file(example_dir, use_local, version)
    python_path = get_python_path(venv_dir)
    site_packages = get_site_packages(venv_dir, python_path)

    if debug:
        console.print(f"Using Python: {python_path}")
        console.print(f"Using site-packages: {site_packages}")

    env = {
        **os.environ,
        "VIRTUAL_ENV": str(venv_dir),
        "PYTHONPATH": f"{str(site_packages)}:{str(project_root)}/src",
    }

    try:
        # Install dependencies using uv
        console.print("Installing dependencies...")

        result = subprocess.run(
            ["uv", "pip", "install", "-r", str(temp_req)],
            cwd=example_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            console.print(f"[red]Error installing dependencies:[/]\n{result.stderr}")
            raise typer.Exit(1)
        else:
            pass
            # status.update("[green]Dependencies installed successfully[/]")

        # Debug: List installed packages
        if debug:
            console.print("\nInstalled packages:")
            subprocess.run(
                ["uv", "pip", "list"],
                cwd=example_dir,
                env=env,
                check=True,
            )

            console.print("\nPython path:")
            subprocess.run(
                [str(python_path), "-c", "import sys; print('\\n'.join(sys.path))"],
                cwd=example_dir,
                env=env,
                check=True,
            )

        # Run the example
        console.print(f"\n[bold green]Running {example_name}[/]\n")
        # status.update(f"Running {example_name}")
        subprocess.run(
            [str(python_path), "main.py"],
            cwd=example_dir,
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error: {e}")
        raise typer.Exit(1)
    finally:
        temp_req.unlink()


@app.command(name="clean")
def clean_env(
    example_path: str | None = typer.Argument(
        None, help="Path to the example to clean (e.g., 'basic/mcp_basic_agent'), or all if not specified"
    ),
):
    """Clean up virtual environments from examples."""
    examples_dir = Path("examples")

    if example_path:
        # Split path into category and example name
        parts = example_path.replace("\\", "/").split("/")
        if len(parts) != 2:
            console.print(f"[red]Invalid example path format: '{example_path}'. Use 'category/example_name'[/]")
            raise typer.Exit(1)
            
        category, example_name = parts
        example_dir = examples_dir / category / example_name
        
        if not example_dir.exists():
            console.print(f"[red]Example '{example_name}' not found in category '{category}'[/]")
            raise typer.Exit(1)
            
        dirs = [example_dir]
    else:
        # Clean all examples in all categories
        dirs = []
        for category_dir in examples_dir.iterdir():
            if not category_dir.is_dir() or category_dir.name.startswith("."):
                continue
                
            for example_dir in category_dir.iterdir():
                if example_dir.is_dir() and not example_dir.name.startswith("."):
                    dirs.append(example_dir)

    for d in dirs:
        clean_venv(d)


if __name__ == "__main__":
    app()
