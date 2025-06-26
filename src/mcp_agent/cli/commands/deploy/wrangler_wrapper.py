import os
from pathlib import Path
import subprocess
import tempfile
import textwrap

from mcp_agent_cloud.config import settings
from mcp_agent_cloud.ux import print_error, print_info
from rich.progress import Progress, SpinnerColumn, TextColumn

from .constants import (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_EMAIL,
    WRANGLER_AUTH_DOMAIN,
    WRANGLER_AUTH_URL,
    WRANGLER_SEND_METRICS,
    CLOUDFLARE_API_BASE_URL,
)


def wrangler_deploy(app_id: str, api_key: str, project_dir: Path) -> str:
    """Bundle the MCP Agent using Wrangler.

    A thin wrapper around the Wrangler CLI to bundle the MCP Agent application code
    and upload it our internal cf storage.

    Some key details here:
    - We must add a temporary `wrangler.toml` to the project directory to set python_workers
      compatibility flag (CLI arg is not sufficient).
    - Python workers with a `requirements.txt` file cannot be published by Wrangler, so we must
      rename any `requirements.txt` file to `requirements-mcp-agent.txt` before bundling.
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
            "WRANGLER_AUTH_DOMAIN": WRANGLER_AUTH_DOMAIN,
            "WRANGLER_AUTH_URL": WRANGLER_AUTH_URL,
            "WRANGLER_SEND_METRICS": str(WRANGLER_SEND_METRICS).lower(),
            "CLOUDFLARE_API_BASE_URL": CLOUDFLARE_API_BASE_URL,
            "HOME": os.path.expanduser(settings.DEPLOYMENT_CACHE_DIR),
            "XDG_HOME_DIR": os.path.expanduser(settings.DEPLOYMENT_CACHE_DIR),
        }
    )

    # TODO: do we require a main.py as the entrypoint?
    main_py = "main.py"

    # Set up a temporary wrangler configuration within the project
    # to ensure compatibility_flags are set correctly.
    wrangler_toml_path = project_dir / "wrangler.toml"

    # Rename requirements.txt if it exists
    original_reqs = project_dir / "requirements.txt"
    temp_reqs = project_dir / "requirements-mcp-agent.txt"
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

    try:
        if original_reqs.exists():
            original_reqs.rename(temp_reqs)
            renamed_reqs = True

        if original_venv.exists():
            temp_dir = tempfile.TemporaryDirectory(prefix="mcp-venv-temp-")
            temp_venv_path = Path(temp_dir.name) / ".venv"
            original_venv.rename(temp_venv_path)
            temp_venv = temp_dir  # keep ref to cleanup later

        wrangler_toml_path.write_text(wrangler_toml_content)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Bundling MCP Agent...", total=None)

            try:
                result = subprocess.run(
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
                print_info(result.stdout)
                return result.stdout.strip()

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

        if wrangler_toml_path.exists():
            wrangler_toml_path.unlink()
