import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import (
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    REQUIREMENTS_TXT_FILENAME,
)
from mcp_agent.cli.utils.ux import print_error

from .constants import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_EMAIL,
    WRANGLER_SEND_METRICS,
)
from .settings import deployment_settings
from .validation import validate_project

_WELL_KNOWN_CONFIG_FILES = [
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    "uv.lock",
    "poetry.lock",
    "pyproject.toml",
    REQUIREMENTS_TXT_FILENAME,
]


def wrangler_deploy(app_id: str, api_key: str, project_dir: Path) -> None:
    """Bundle the MCP Agent using Wrangler.

    A thin wrapper around the Wrangler CLI to bundle the MCP Agent application code
    and upload it our internal cf storage.

    Some key details here:
    - We must add a temporary `wrangler.toml` to the project directory to set python_workers
      compatibility flag (CLI arg is not sufficient).
    - Python workers with a `requirements.txt` file cannot be published by Wrangler, so we must
      rename any `requirements.txt` file to `requirements.txt.mcpac.py` before bundling
    - Non-python files (e.g. `uv.lock`, `poetry.lock`, `pyproject.toml`) would be excluded by default
    due to no py extension, so they are also copied with a `.mcpac.py` extension.
    - Similarly, having a `.venv` in the python project directory will result in the same error as
      `requirements.txt`, so we temporarily move it out of the project directory if it exists.

    Args:
        app_id (str): The application ID.
        api_key (str): User MCP Agent Cloud API key.
        project_dir (Path): The directory of the project to deploy.
    """

    # Copy existing env to avoid overwriting
    env = os.environ.copy()

    env.update(
        {
            "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID,
            "CLOUDFLARE_API_TOKEN": api_key,
            "CLOUDFLARE_EMAIL": CLOUDFLARE_EMAIL,
            "WRANGLER_AUTH_DOMAIN": deployment_settings.wrangler_auth_domain,
            "WRANGLER_AUTH_URL": deployment_settings.wrangler_auth_url,
            "WRANGLER_SEND_METRICS": str(WRANGLER_SEND_METRICS).lower(),
            "CLOUDFLARE_API_BASE_URL": deployment_settings.cloudflare_api_base_url,
            "HOME": os.path.expanduser(settings.DEPLOYMENT_CACHE_DIR),
            "XDG_HOME_DIR": os.path.expanduser(settings.DEPLOYMENT_CACHE_DIR),
        }
    )

    validate_project(project_dir)

    # We require main.py to be present as the entrypoint / app definition
    main_py = "main.py"

    # Set up a temporary wrangler configuration within the project
    # to ensure compatibility_flags are set correctly.
    wrangler_toml_path = project_dir / "wrangler.toml"

    # Rename requirements.txt if it exists
    original_reqs = project_dir / REQUIREMENTS_TXT_FILENAME
    temp_reqs = project_dir / ".requirements.txt.bak"
    renamed_reqs = False

    # Temporarily move .venv if it exists
    original_venv = project_dir / ".venv"
    temp_venv = None

    # Create temporary wrangler.toml
    wrangler_toml_content = textwrap.dedent(
        f"""
        name = "{app_id}"
        main = "{main_py}"
        compatibility_flags = ["python_workers"]
        compatibility_date = "2025-06-26"
    """
    ).strip()

    copied_py_files = []  # Track all files we copy with .py extension

    try:
        if original_venv.exists():
            temp_dir = tempfile.TemporaryDirectory(prefix="mcp-venv-temp-")
            temp_venv_path = Path(temp_dir.name) / ".venv"
            original_venv.rename(temp_venv_path)
            temp_venv = temp_dir  # keep ref to cleanup later

        # Copy well-known config files with a .mcpac.py extension whenever they exist
        for filename in _WELL_KNOWN_CONFIG_FILES:
            file_path = project_dir / filename
            if file_path.exists():
                py_path = project_dir / f"{filename}.mcpac.py"
                shutil.copy(file_path, py_path)
                copied_py_files.append(py_path)

                # In the special case of requirements.txt, we still have to hide the original file
                if filename == REQUIREMENTS_TXT_FILENAME:
                    file_path.rename(temp_reqs)
                    renamed_reqs = True

        wrangler_toml_path.write_text(wrangler_toml_content)

        with Progress(
            SpinnerColumn(spinner_name="aesthetic"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Bundling MCP Agent...", total=None)

            try:
                subprocess.run(
                    [
                        "npx",
                        "--yes",
                        "wrangler@4.22.0",
                        "deploy",
                        main_py,
                        "--name",
                        app_id,
                        "--no-bundle",
                    ],
                    check=True,
                    env=env,
                    cwd=str(project_dir),
                    capture_output=True,
                    text=True,
                )
                progress.update(task, description="✅ Bundled successfully")
                return

            except subprocess.CalledProcessError as e:
                progress.update(task, description="❌ Bundling failed")
                print_error("Error output:")
                print_error(e.stderr or "No error output.")
                raise

    finally:
        if renamed_reqs and temp_reqs.exists():
            temp_reqs.rename(original_reqs)

        if temp_venv is not None:
            temp_venv_path.rename(original_venv)
            temp_venv.cleanup()

        # Remove all copied .py files
        for py_file in copied_py_files:
            if py_file.exists():
                os.remove(py_file)

        if wrangler_toml_path.exists():
            wrangler_toml_path.unlink()
