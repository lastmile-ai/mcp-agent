import os
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


def wrangler_deploy(api_key: str):
    """Deploy the MCP Agent using Wrangler."""

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
        task = progress.add_task("Deploying MCP Agent...", total=None)

        try:
            result = subprocess.run(
                ["npx", "wrangler", "deploy"],
                check=True,
                env=env,
                capture_output=True,
                text=True,
            )
            progress.update(task, description="✅ Deployed successfully")
            print_info(result.stdout)
        except subprocess.CalledProcessError as e:
            progress.update(task, description="❌ Deployment failed")
            print_error("Error output:")
            print_error(e.stderr or "No error output.")
            raise
