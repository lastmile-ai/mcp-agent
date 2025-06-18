import os
from pathlib import Path
import subprocess

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
    """Bundle the MCP Agent using Wrangler."""

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

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task = progress.add_task("Bundling MCP Agent...", total=None)

        # TODO: do we require a main.py as the entrypoint?
        main_py = "main.py"
        try:
            result = subprocess.run(
                [
                    "npx",
                    "wrangler",
                    "deploy",
                    main_py,
                    "--name",
                    app_id,
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
                cwd=str(project_dir),
            )
            progress.update(task, description="✅ Bundled successfully")
            print_info(result.stdout)

            # TODO: Return the source URI
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            progress.update(task, description="❌ Bundling failed")
            print_error("Error output:")
            print_error(e.stderr or "No error output.")
            raise
