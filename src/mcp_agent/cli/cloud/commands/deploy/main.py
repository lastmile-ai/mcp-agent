"""Deploy command for MCP Agent Cloud CLI.

This module provides the deploy_config function which processes configuration files
with secret tags and transforms them into deployment-ready configurations with secret handles.
"""

from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    ENV_API_BASE_URL,
    ENV_API_KEY,
    MCP_CONFIG_FILENAME,
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPAppClient
from mcp_agent.cli.secrets.processor import (
    process_config_secrets,
)
from mcp_agent.cli.utils.retry import retry_async_with_exponential_backoff, RetryError
from mcp_agent.cli.utils.ux import (
    console,
    print_deployment_header,
    print_error,
    print_info,
    print_success,
)
from mcp_agent.cli.utils.git_utils import (
    get_git_metadata,
    create_git_tag,
    sanitize_git_ref_component,
)

from .wrangler_wrapper import wrangler_deploy


def deploy_config(
    ctx: typer.Context,
    app_name: Optional[str] = typer.Argument(
        None,
        help="Name of the MCP App to deploy.",
    ),
    app_description: Optional[str] = typer.Option(
        None,
        "--app-description",
        "-d",
        help="Description of the MCP App being deployed.",
    ),
    config_dir: Path = typer.Option(
        Path(""),
        "--config-dir",
        "-c",
        help="Path to the directory containing the app config and app files.",
        exists=True,
        readable=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Use existing secrets and update existing app where applicable, without prompting.",
    ),
    # TODO(@rholinshead): Re-add dry-run and perform pre-validation of the app
    # dry_run: bool = typer.Option(
    #     False,
    #     "--dry-run",
    #     help="Validate the deployment but don't actually deploy.",
    # ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
        envvar=ENV_API_BASE_URL,
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
        envvar=ENV_API_KEY,
    ),
    git_tag: bool = typer.Option(
        False,
        "--git-tag/--no-git-tag",
        help="Create a local git tag for this deploy (if in a git repo)",
        envvar="MCP_DEPLOY_GIT_TAG",
    ),
    retry_count: int = typer.Option(
        3,
        "--retry-count",
        help="Number of retries on deployment failure.",
        min=1,
        max=10,
    ),
) -> str:
    """Deploy an MCP agent using the specified configuration.

    An MCP App is deployed from bundling the code at the specified config directory.
    This directory must contain an 'mcp_agent.config.yaml' at its root. The process will look for an existing
    'mcp_agent.deployed.secrets.yaml' in the config directory or create one by processing the 'mcp_agent.secrets.yaml'
    in the config directory (if it exists) and prompting for desired secrets usage.
    The 'deployed' secrets file is processed to replace raw secrets with secret handles before deployment and
    that file is included in the deployment bundle in place of the original secrets file.

    Args:
        app_name: Name of the MCP App to deploy
        app_description: Description of the MCP App being deployed
        config_dir: Path to the directory containing the app configuration files
        non_interactive: Never prompt for reusing or updating secrets or existing apps; reuse existing where possible
        api_url: API base URL
        api_key: API key for authentication
        retry_count: Number of retries on deployment failure

    Returns:
        Newly-deployed MCP App ID
    """
    # Show help if no app_name is provided
    if app_name is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    try:
        provided_key = api_key
        effective_api_url = api_url or settings.API_BASE_URL
        effective_api_key = (
            provided_key or settings.API_KEY or load_api_key_credentials()
        )

        if not effective_api_url:
            raise CLIError(
                "MCP_API_BASE_URL environment variable or --api-url option must be set.",
                retriable=False,
            )
        if not effective_api_key:
            raise CLIError(
                "Must be logged in to deploy. Run 'mcp-agent login', set MCP_API_KEY environment variable or specify --api-key option.",
                retriable=False,
            )
        print_info(f"Using API at {effective_api_url}")

        mcp_app_client = MCPAppClient(
            api_url=effective_api_url, api_key=effective_api_key
        )

        print_info(f"Checking for existing app ID for '{app_name}'...")
        try:
            app_id = run_async(mcp_app_client.get_app_id_by_name(app_name))
            if not app_id:
                print_info(
                    f"No existing app found with name '{app_name}'. Creating a new app..."
                )
                app = run_async(
                    mcp_app_client.create_app(
                        name=app_name, description=app_description
                    )
                )
                app_id = app.appId
                print_success(f"Created new app with ID: {app_id}")
            else:
                print_success(
                    f"Found existing app with ID: {app_id} for name '{app_name}'"
                )
                if not non_interactive:
                    use_existing = typer.confirm(
                        f"Do you want deploy an update to the existing app ID: {app_id}?"
                    )
                    if use_existing:
                        print_info(f"Will deploy an update to app ID: {app_id}")
                    else:
                        print_error(
                            "Cancelling deployment. Please choose a different app name."
                        )
                        return app_id
                else:
                    print_info(
                        "--non-interactive specified, will deploy an update to the existing app."
                    )
        except UnauthenticatedError as e:
            raise CLIError(
                "Invalid API key for deployment. Run 'mcp-agent login' or set MCP_API_KEY environment variable with new API key.",
                retriable=False,
            ) from e
        except Exception as e:
            raise CLIError(f"Error checking or creating app: {str(e)}") from e

        # Validate config directory and required files
        config_file, secrets_file, deployed_secrets_file = get_config_files(config_dir)

        # If a deployed secrets file already exists, determine if it should be used or overwritten
        if deployed_secrets_file:
            if secrets_file:
                print_info(
                    f"Both '{MCP_SECRETS_FILENAME}' and '{MCP_DEPLOYED_SECRETS_FILENAME}' found in {config_dir}."
                )
                if non_interactive:
                    print_info(
                        "--non-interactive specified, using existing deployed secrets file without changes."
                    )
                else:
                    update = typer.confirm(
                        f"Do you want to update the existing '{MCP_DEPLOYED_SECRETS_FILENAME}' by re-processing '{MCP_SECRETS_FILENAME}'?"
                    )
                    if update:
                        print_info(
                            f"Will update existing '{MCP_DEPLOYED_SECRETS_FILENAME}' by re-processing '{MCP_SECRETS_FILENAME}'."
                        )
                        deployed_secrets_file = None  # Will trigger re-processing
                    else:
                        print_info(f"Using existing '{MCP_DEPLOYED_SECRETS_FILENAME}'.")
            else:
                print_info(
                    f"Found '{MCP_DEPLOYED_SECRETS_FILENAME}' in {config_dir}, but no '{MCP_SECRETS_FILENAME}' to re-process. Using existing deployed secrets file."
                )

        print_deployment_header(
            app_name, app_id, config_file, secrets_file, deployed_secrets_file
        )

        secrets_transformed_path = None
        if secrets_file and not deployed_secrets_file:
            print_info("Processing secrets file...")
            secrets_transformed_path = Path(
                f"{config_dir}/{MCP_DEPLOYED_SECRETS_FILENAME}"
            )

            run_async(
                process_config_secrets(
                    input_path=secrets_file,
                    output_path=secrets_transformed_path,
                    api_url=effective_api_url,
                    api_key=effective_api_key,
                    non_interactive=non_interactive,
                )
            )

            print_success("Secrets file processed successfully")
            print_info(
                f"Transformed secrets file written to {secrets_transformed_path}"
            )

        else:
            print_info("Skipping secrets processing...")

        console.print(
            Panel(
                "Ready to deploy MCP Agent with processed configuration",
                title="Deployment Ready",
                border_style="green",
            )
        )

        # Optionally create a local git tag as a breadcrumb of this deployment
        if git_tag:
            git_meta = get_git_metadata(config_dir)
            if git_meta:
                # Sanitize app name for git tag safety
                safe_name = sanitize_git_ref_component(app_name)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                tag_name = f"mcp-deploy/{safe_name}/{ts}-{git_meta.short_sha}"
                msg = (
                    f"MCP Agent deploy for app '{app_name}' (id {app_id})\n"
                    f"Commit: {git_meta.commit_sha}\n"
                    f"Branch: {git_meta.branch or ''}\n"
                    f"Dirty: {git_meta.dirty}"
                )
                if create_git_tag(config_dir, tag_name, msg):
                    print_success(f"Created local git tag: {tag_name}")
                else:
                    print_info("Skipping git tag (not a repo or tag failed)")
            else:
                print_info("Skipping git tag (not a git repository)")

        app = run_async(
            _deploy_with_retry(
                app_id=app_id,
                api_key=effective_api_key,
                project_dir=config_dir,
                mcp_app_client=mcp_app_client,
                retry_count=retry_count,
            )
        )

        print_info(f"App ID: {app_id}")
        if app.appServerInfo:
            status = (
                "ONLINE"
                if app.appServerInfo.status == "APP_SERVER_STATUS_ONLINE"
                else "OFFLINE"
            )
            print_info(f"App URL: {app.appServerInfo.serverUrl}")
            print_info(f"App Status: {status}")
        return app_id

    except Exception as e:
        if settings.VERBOSE:
            import traceback

            typer.echo(traceback.format_exc())
        raise CLIError(f"Deployment failed: {str(e)}") from e


async def _deploy_with_retry(
    app_id: str,
    api_key: str,
    project_dir: Path,
    mcp_app_client: MCPAppClient,
    retry_count: int,
):
    """Execute the deployment operations with retry logic.

    Args:
        app_id: The application ID
        api_key: API key for authentication
        project_dir: Directory containing the project files
        mcp_app_client: MCP App client for API calls
        retry_count: Number of retry attempts for deployment

    Returns:
        Deployed app information
    """
    # Step 1: Bundle once (no retry - if this fails, fail immediately)
    try:
        wrangler_deploy(
            app_id=app_id,
            api_key=api_key,
            project_dir=project_dir,
        )
    except Exception as e:
        raise CLIError(f"Bundling failed: {str(e)}") from e

    # Step 2: Deployment API call with retries if needed
    attempt = 0

    async def _perform_api_deployment():
        nonlocal attempt
        attempt += 1

        attempt_suffix = f" (attempt {attempt}/{retry_count})" if attempt > 1 else ""

        with Progress(
            SpinnerColumn(spinner_name="arrow3"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            deploy_task = progress.add_task(
                f"Deploying MCP App bundle{attempt_suffix}...", total=None
            )
            try:
                # Optionally include minimal metadata (git only to avoid heavy scans)
                metadata = None
                gm = get_git_metadata(project_dir)
                if gm:
                    metadata = {
                        "source": "git",
                        "commit": gm.commit_sha,
                        "short": gm.short_sha,
                        "branch": gm.branch,
                        "dirty": gm.dirty,
                        "tag": gm.tag,
                        "message": gm.commit_message,
                    }

                try:
                    app = await mcp_app_client.deploy_app(
                        app_id=app_id, deployment_metadata=metadata
                    )
                except Exception as e:
                    # Fallback: if API rejects deploymentMetadata, retry once without it
                    try:
                        app = await mcp_app_client.deploy_app(
                            app_id=app_id, deployment_metadata=None
                        )
                    except Exception:
                        raise e
                progress.update(
                    deploy_task,
                    description=f"✅ MCP App deployed successfully{attempt_suffix}!",
                )
                return app
            except Exception:
                progress.update(
                    deploy_task, description=f"❌ Deployment failed{attempt_suffix}"
                )
                raise

    if retry_count > 1:
        print_info(f"Deployment API configured with up to {retry_count} attempts")

    try:
        return await retry_async_with_exponential_backoff(
            _perform_api_deployment,
            max_attempts=retry_count,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            max_delay=30.0,
        )
    except RetryError as e:
        attempts_text = "attempts" if retry_count > 1 else "attempt"
        print_error(f"Deployment failed after {retry_count} {attempts_text}")
        raise CLIError(
            f"Deployment failed after {retry_count} {attempts_text}. Last error: {e.original_error}"
        ) from e.original_error


def get_config_files(config_dir: Path) -> tuple[Path, Optional[Path], Optional[Path]]:
    """Get the configuration and secrets files from the configuration directory.

    Args:
        config_dir: Directory containing the configuration files

    Returns:
        Tuple of (config_file_path, secrets_file_path or None, deployed_secrets_file_path or None)
    """

    config_file = config_dir / MCP_CONFIG_FILENAME
    if not config_file.exists():
        raise CLIError(
            f"Configuration file '{MCP_CONFIG_FILENAME}' not found in {config_dir}",
            retriable=False,
        )

    secrets_file: Optional[Path] = None
    deployed_secrets_file: Optional[Path] = None

    secrets_path = config_dir / MCP_SECRETS_FILENAME
    deployed_secrets_path = config_dir / MCP_DEPLOYED_SECRETS_FILENAME

    if secrets_path.exists():
        secrets_file = secrets_path

    if deployed_secrets_path.exists():
        deployed_secrets_file = deployed_secrets_path

    return config_file, secrets_file, deployed_secrets_file
