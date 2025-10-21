"""
Install command for adding MCP servers to client applications.

Similar to fastmcp install, this command provides end-to-end installation:
1. Authenticates with MCP Agent Cloud
2. Configures server with required secrets
3. Writes server configuration to client config file

Supported clients:
 - vscode: writes .vscode/mcp.json in project
 - claude_code: writes ~/.claude/claude_code_config.json
 - cursor: writes ~/.cursor/mcp.json
 - claude_desktop: writes ~/.claude/mcp.json (Claude Desktop)
 - chatgpt: prints configuration instructions
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
    MCP_CONFIGURED_SECRETS_FILENAME,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPAppClient
from mcp_agent.cli.mcp_app.mock_client import MockMCPAppClient
from mcp_agent.cli.secrets.mock_client import MockSecretsClient
from mcp_agent.cli.secrets.processor import configure_user_secrets
from mcp_agent.cli.utils.ux import (
    console,
    print_configuration_header,
    print_info,
    print_success,
    print_warning,
)

app = typer.Typer(help="Install MCP server to client applications")


CLIENT_CONFIGS = {
    "vscode": {
        "path": lambda: Path.cwd() / ".vscode" / "mcp.json",
        "description": "VSCode (project-local)",
    },
    "claude_code": {
        "path": lambda: Path.home() / ".claude" / "claude_code_config.json",
        "description": "Claude Code",
    },
    "cursor": {
        "path": lambda: Path.home() / ".cursor" / "mcp.json",
        "description": "Cursor",
    },
    "claude_desktop": {
        "path": lambda: Path.home() / ".claude" / "mcp.json",
        "description": "Claude Desktop",
    },
}


def _merge_mcp_json(existing: dict, server_name: str, server_config: dict) -> dict:
    """
    Merge a server configuration into existing MCP JSON.
    Accepts various formats and always emits {"mcp":{"servers":{...}}}.
    """
    servers: dict = {}
    if isinstance(existing, dict):
        if "mcp" in existing and isinstance(existing.get("mcp"), dict):
            servers = dict(existing["mcp"].get("servers") or {})
        elif "servers" in existing and isinstance(existing.get("servers"), dict):
            servers = dict(existing.get("servers") or {})
        else:
            for k, v in existing.items():
                if isinstance(v, dict) and ("url" in v or "transport" in v):
                    servers[k] = v

    servers[server_name] = server_config
    return {"mcp": {"servers": servers}}


def _write_json(path: Path, data: dict) -> None:
    """Write JSON data to file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_server_config(server_url: str, transport: str = "http") -> dict:
    """Build server configuration dictionary."""
    return {
        "url": server_url,
        "transport": transport,
    }


def _generate_server_name(server_url: str) -> str:
    """Generate a server name from URL."""
    # Extract meaningful part from URL
    # e.g., https://api.example.com/servers/my-server/mcp -> my-server
    parts = server_url.rstrip("/").split("/")

    # If URL has path segments (more than protocol://domain)
    if len(parts) > 3:  # ['https:', '', 'domain', 'path', ...]
        # Try to get the second-to-last meaningful part
        # Skip common MCP path segments
        path_parts = [p for p in parts[3:] if p and p not in ('mcp', 'sse')]
        if path_parts:
            return path_parts[-1]

    # Fall back to domain name
    if len(parts) >= 3:
        domain = parts[2]
        domain = domain.split(':')[0]
        return domain

    return "server"


@app.callback(invoke_without_command=True)
def install(
    server_identifier: str = typer.Argument(
        ..., help="Server URL, app ID, or app name to install"
    ),
    client: str = typer.Option(
        ..., "--client", "-c", help="Client to install to: vscode|claude_code|cursor|claude_desktop|chatgpt"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Server name in client config (auto-generated if not provided)"
    ),
    secrets_file: Optional[Path] = typer.Option(
        None,
        "--secrets-file",
        "-s",
        help="Path to secrets.yaml file with user secret IDs. If not provided, secrets will be prompted interactively.",
        exists=True,
        readable=True,
        dir_okay=False,
        resolve_path=True,
    ),
    secrets_output_file: Optional[Path] = typer.Option(
        None,
        "--secrets-output-file",
        "-o",
        help="Path to write configured secrets. Defaults to mcp_agent.configured.secrets.yaml",
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate configuration but don't install"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing server configuration"
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL",
        envvar=ENV_API_BASE_URL,
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication",
        envvar=ENV_API_KEY,
    ),
) -> None:
    """
    Install an MCP server to a client application.

    This command:
    1. Authenticates with MCP Agent Cloud
    2. Configures the server with required secrets
    3. Writes the server configuration to the client's config file

    Examples:
        # Install to VSCode
        mcp-agent install https://api.example.com/servers/my-server/mcp --client vscode

        # Install to Claude Code with custom name
        mcp-agent install app-id-123 --client claude_code --name my-server

        # Install with existing secrets file
        mcp-agent install my-server --client cursor --secrets-file secrets.yaml
    """
    client_lc = client.lower()

    if client_lc not in CLIENT_CONFIGS and client_lc != "chatgpt":
        raise CLIError(
            f"Unsupported client: {client}. Supported clients: vscode, claude_code, cursor, claude_desktop, chatgpt"
        )

    effective_api_key = api_key or settings.API_KEY or load_api_key_credentials()
    if not effective_api_key:
        raise CLIError(
            "Must be logged in to install. Run 'mcp-agent login', set MCP_API_KEY environment variable, or specify --api-key option."
        )

    mcp_client: Union[MockMCPAppClient, MCPAppClient]
    if dry_run:
        print_info("Using MOCK API client for dry run")
        mcp_client = MockMCPAppClient(
            api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
        )
    else:
        mcp_client = MCPAppClient(
            api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
        )

    if secrets_file and secrets_output_file:
        raise CLIError(
            "Cannot provide both --secrets-file and --secrets-output-file. Please specify only one."
        )
    if secrets_file and not secrets_file.suffix == ".yaml":
        raise CLIError(
            "The --secrets-file must be a YAML file. Please provide a valid path."
        )
    if secrets_output_file and not secrets_output_file.suffix == ".yaml":
        raise CLIError(
            "The --secrets-output-file must be a YAML file. Please provide a valid path."
        )

    # Normalize server identifier to URL
    app_server_url = server_identifier
    if not server_identifier.startswith("http://") and not server_identifier.startswith("https://"):
        # Could be app ID or name - try to resolve via API
        # For now, treat as URL and let API handle validation
        # In future, could add app lookup by ID/name
        print_warning(
            f"Treating '{server_identifier}' as server URL. If this is an app ID/name, URL resolution is not yet implemented."
        )

    console.print(f"\n[bold cyan]Installing MCP Server[/bold cyan]\n")
    print_info(f"Server: {app_server_url}")
    print_info(f"Client: {CLIENT_CONFIGS.get(client_lc, {}).get('description', client_lc)}")

    required_params = []
    try:
        with Progress(
            SpinnerColumn(spinner_name="arrow3"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Checking server requirements...", total=None)
            required_params = run_async(
                mcp_client.list_config_params(app_server_url=app_server_url)
            )
            progress.update(task, description="✅ Server requirements checked")
    except UnauthenticatedError as e:
        raise CLIError(
            "Invalid API key. Run 'mcp-agent login' or set MCP_API_KEY environment variable."
        ) from e
    except Exception as e:
        raise CLIError(
            f"Failed to retrieve server requirements: {e}"
        ) from e

    configured_secrets = {}
    requires_secrets = len(required_params) > 0

    if requires_secrets:
        if not secrets_file and secrets_output_file is None:
            secrets_output_file = Path(MCP_CONFIGURED_SECRETS_FILENAME)
            print_info(f"Using default secrets output: {secrets_output_file}")

        print_configuration_header(secrets_file, secrets_output_file, dry_run)
        print_info(
            f"Server requires {len(required_params)} secret(s): {', '.join(required_params)}"
        )

        try:
            print_info("Processing user secrets...")

            if dry_run:
                print_info("Using MOCK Secrets API client for dry run")
                mock_secrets_client = MockSecretsClient(
                    api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
                )
                configured_secrets = run_async(
                    configure_user_secrets(
                        required_secrets=required_params,
                        config_path=secrets_file,
                        output_path=secrets_output_file,
                        client=mock_secrets_client,
                    )
                )
            else:
                configured_secrets = run_async(
                    configure_user_secrets(
                        required_secrets=required_params,
                        config_path=secrets_file,
                        output_path=secrets_output_file,
                        api_url=api_url,
                        api_key=effective_api_key,
                    )
                )

            print_success("User secrets processed successfully")

        except Exception as e:
            if settings.VERBOSE:
                import traceback
                typer.echo(traceback.format_exc())
            raise CLIError(f"Failed to process secrets: {e}") from e
    else:
        print_info("Server does not require any secrets")
        if secrets_file:
            raise CLIError(
                f"Server does not require secrets, but a secrets file was provided: {secrets_file}"
            )

    if dry_run:
        print_success("Installation completed in dry run mode (no files written)")
        return

    configured_server_url = app_server_url
    try:
        with Progress(
            SpinnerColumn(spinner_name="arrow3"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Configuring server...", total=None)
            config = run_async(
                mcp_client.configure_app(
                    app_server_url=app_server_url, config_params=configured_secrets
                )
            )
            progress.update(task, description="✅ Server configured")

            if config.appServerInfo and config.appServerInfo.serverUrl:
                configured_server_url = config.appServerInfo.serverUrl
                print_info(f"Configured server URL: {configured_server_url}")

    except Exception as e:
        raise CLIError(f"Failed to configure server: {e}") from e

    if client_lc == "chatgpt":
        console.print(
            Panel(
                f"[bold]ChatGPT Configuration Instructions[/bold]\n\n"
                f"1. Open ChatGPT settings\n"
                f"2. Navigate to MCP Servers section\n"
                f"3. Add a new server with:\n"
                f"   - URL: [cyan]{configured_server_url}[/cyan]\n"
                f"   - Transport: [cyan]http[/cyan]",
                title="Manual Configuration Required",
                border_style="yellow",
            )
        )
        return

    client_config = CLIENT_CONFIGS[client_lc]
    config_path = client_config["path"]()

    server_name = name or _generate_server_name(configured_server_url)

    existing_config = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
            servers = existing_config.get("mcp", {}).get("servers", {})
            if server_name in servers and not force:
                raise CLIError(
                    f"Server '{server_name}' already exists in {config_path}. Use --force to overwrite."
                )
        except json.JSONDecodeError as e:
            raise CLIError(f"Failed to parse existing config at {config_path}: {e}") from e

    transport = "sse" if configured_server_url.rstrip("/").endswith("/sse") else "http"
    server_config = _build_server_config(configured_server_url, transport)

    merged_config = _merge_mcp_json(existing_config, server_name, server_config)

    try:
        _write_json(config_path, merged_config)
        print_success(f"Server '{server_name}' installed to {config_path}")
    except Exception as e:
        raise CLIError(f"Failed to write config file: {e}") from e

    console.print(
        Panel(
            f"[bold green]✅ Installation Complete![/bold green]\n\n"
            f"Server: [cyan]{server_name}[/cyan]\n"
            f"URL: [cyan]{configured_server_url}[/cyan]\n"
            f"Client: [cyan]{client_config['description']}[/cyan]\n"
            f"Config: [cyan]{config_path}[/cyan]\n\n"
            f"[dim]The server is now available in your {client_config['description']} client.[/dim]",
            title="MCP Server Installed",
            border_style="green",
        )
    )
