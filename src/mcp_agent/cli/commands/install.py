"""
Install command for adding MCP servers to client applications.

This command adds deployed MCP Agent Cloud servers to client config files.
For authenticated clients (Claude Code, Cursor, VSCode, Claude Desktop), the
server URL is added with an Authorization header using your MCP_API_KEY.

For ChatGPT, the server must have unauthenticated access enabled.

Supported clients:
 - vscode: writes .vscode/mcp.json
 - claude_code: integrated via 'claude mcp add'
 - cursor: writes ~/.cursor/mcp.json
 - claude_desktop: writes platform-specific config using mcp-remote wrapper
   - macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
   - Windows: ~/AppData/Roaming/Claude/claude_desktop_config.json
   - Linux: ~/.config/Claude/claude_desktop_config.json
 - chatgpt: requires unauthenticated access enabled
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer
from rich.panel import Panel

from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import (
    DEFAULT_API_BASE_URL,
    ENV_API_BASE_URL,
    ENV_API_KEY,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPAppClient
from mcp_agent.cli.utils.ux import (
    console,
    print_info,
    print_success,
)


def _get_claude_desktop_config_path() -> Path:
    """Get the Claude Desktop config path based on platform."""
    if platform.system() == "Darwin":  # macOS
        return (
            Path.home()
            / "Library/Application Support/Claude/claude_desktop_config.json"
        )
    elif platform.system() == "Windows":
        return Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config/Claude/claude_desktop_config.json"


# Client configuration paths
CLIENT_CONFIGS = {
    "vscode": {
        "path": lambda: Path.cwd() / ".vscode" / "mcp.json",
        "description": "VSCode (project-local)",
    },
    "claude_code": {
        "path": lambda: Path.home() / ".claude.json",
        "description": "Claude Code",
    },
    "cursor": {
        "path": lambda: Path.home() / ".cursor" / "mcp.json",
        "description": "Cursor",
    },
    "claude_desktop": {
        "path": _get_claude_desktop_config_path,
        "description": "Claude Desktop",
    },
}


def _merge_mcp_json(
    existing: dict, server_name: str, server_config: dict, format_type: str = "mcp"
) -> dict:
    """
    Merge a server configuration into existing MCP JSON.

    Args:
        existing: Existing config dict
        server_name: Name of the server to add/update
        server_config: Server configuration dict
        format_type: Format to use:
                    - "mcpServers" for Claude Desktop/Cursor
                    - "vscode" for VSCode
                    - "mcp" for other clients
    """
    servers: dict = {}
    other_keys: dict = {}

    if isinstance(existing, dict):
        if "mcpServers" in existing and isinstance(existing.get("mcpServers"), dict):
            servers = dict(existing["mcpServers"])
        elif "servers" in existing and isinstance(existing.get("servers"), dict):
            servers = dict(existing["servers"])
            for k, v in existing.items():
                if k != "servers":
                    other_keys[k] = v
        elif "mcp" in existing and isinstance(existing.get("mcp"), dict):
            servers = dict(existing["mcp"].get("servers") or {})
        else:
            for k, v in existing.items():
                if isinstance(v, dict) and (
                    "url" in v or "transport" in v or "command" in v or "type" in v
                ):
                    servers[k] = v

    servers[server_name] = server_config

    if format_type == "mcpServers":
        return {"mcpServers": servers}
    elif format_type == "vscode":
        result = {"servers": servers}
        if "inputs" not in other_keys:
            result["inputs"] = []
        result.update(other_keys)
        return result
    else:
        return {"mcp": {"servers": servers}}


def _redact_secrets(data: dict) -> dict:
    """Mask Authorization values and mcp-remote header args for safe display."""
    red = deepcopy(data)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "authorization" and isinstance(v, str):
                    obj[k] = "Bearer ***"
                else:
                    walk(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str) and v.lower().startswith(
                    "authorization: bearer "
                ):
                    obj[i] = "Authorization: Bearer ***"
                else:
                    walk(v)

    walk(red)
    return red


def _write_json(path: Path, data: dict) -> None:
    """Write JSON atomically and restrict permissions (secrets inside)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    original_mode = None
    if path.exists() and os.name == "posix":
        original_mode = os.stat(path).st_mode & 0o777

    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))
        os.replace(tmp_name, path)  # atomic on same fs
        if os.name == "posix":
            os.chmod(path, original_mode if original_mode is not None else 0o600)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except Exception:
            pass


def _server_hostname(server_url: str, app_name: Optional[str] = None) -> str:
    """
    Generate a friendly server name from the URL.

    Extracts the subdomain or hostname to create a short, readable name.
    For example, "https://abc123.deployments.mcp-agent.com/sse" -> "abc123"

    Args:
        server_url: The server URL
        app_name: Optional app name from API (preferred if available)

    Returns:
        A friendly server name
    """
    if app_name:
        return app_name

    parsed = urlparse(server_url)
    hostname = parsed.hostname or ""

    parts = hostname.split(".")
    if len(parts) > 2 and "deployments" in hostname:
        return parts[0]

    if len(parts) >= 2:
        return ".".join(parts[:-1])

    return hostname or "mcp-server"


def _build_server_config(
    server_url: str,
    transport: str = "http",
    for_claude_desktop: bool = False,
    for_vscode: bool = False,
    api_key: str = None,
) -> dict:
    """Build server configuration dictionary with auth header.

    For Claude Desktop, wraps HTTP/SSE servers with mcp-remote stdio wrapper with actual API key.
    For VSCode, uses "type" field and top-level "servers" structure.
    For other clients (Cursor), uses "transport" field with "mcpServers" top-level structure.

    Args:
        server_url: The server URL
        transport: Transport type (http or sse)
        for_claude_desktop: Whether to use Claude Desktop format with mcp-remote
        for_vscode: Whether to use VSCode format with "type" field
        api_key: The actual API key (required for all clients)
    """
    if not api_key:
        raise ValueError("API key is required for server configuration")

    if for_claude_desktop:
        # Claude Desktop requires stdio wrapper using mcp-remote with actual API key
        return {
            "command": "npx",
            "args": [
                "mcp-remote",
                server_url,
                "--header",
                f"Authorization: Bearer {api_key}",
            ],
        }
    elif for_vscode:
        # VSCode uses "type" instead of "transport"
        return {
            "type": transport,
            "url": server_url,
            "headers": {"Authorization": f"Bearer {api_key}"},
        }
    else:
        # Direct HTTP/SSE connection for Cursor with embedded API key
        return {
            "url": server_url,
            "transport": transport,
            "headers": {"Authorization": f"Bearer {api_key}"},
        }


def install(
    server_identifier: str = typer.Argument(..., help="Server URL to install"),
    client: str = typer.Option(
        ...,
        "--client",
        "-c",
        help="Client to install to: vscode|claude_code|cursor|claude_desktop|chatgpt",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Server name in client config (auto-generated if not provided)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be installed without writing files"
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

    This command writes the server configuration to the client's config file.
    For authenticated clients (everything except ChatGPT), the server URL is
    added with an Authorization header using your MCP_API_KEY environment variable.

    URLs without /sse or /mcp suffix will automatically have /sse appended and
    use SSE transport for optimal performance.

    For ChatGPT, the server must have unauthenticated access enabled.

    Examples:
        # Install to VSCode (automatically appends /sse)
        mcp-agent install --client=vscode https://xxx.deployments.mcp-agent.com

        # Install to Claude Code with custom name
        mcp-agent install --client=claude_code --name=my-server https://xxx.deployments.mcp-agent.com

        # Install to ChatGPT (requires unauthenticated access)
        mcp-agent install --client=chatgpt https://xxx.deployments.mcp-agent.com
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

    server_url = server_identifier
    if not server_identifier.startswith("http://") and not server_identifier.startswith(
        "https://"
    ):
        raise CLIError(
            f"Server identifier must be a URL starting with http:// or https://. Got: {server_identifier}"
        )

    if not server_url.endswith("/sse") and not server_url.endswith("/mcp"):
        server_url = server_url.rstrip("/") + "/sse"
        print_info(f"Using SSE transport: {server_url}")

    console.print("\n[bold cyan]Installing MCP Server[/bold cyan]\n")
    print_info(f"Server URL: {server_url}")
    print_info(
        f"Client: {CLIENT_CONFIGS.get(client_lc, {}).get('description', client_lc)}"
    )

    mcp_client = MCPAppClient(
        api_url=api_url or DEFAULT_API_BASE_URL, api_key=effective_api_key
    )

    try:
        app_info = run_async(mcp_client.get_app(server_url=server_url))
        app_name = app_info.name if app_info else None
        print_info(f"App name: {app_name}")
    except Exception as e:
        print_info(f"Warning: Could not fetch app info: {e}")
        app_name = None

    # For ChatGPT, check if server has unauthenticated access enabled
    if client_lc == "chatgpt":
        try:
            if not app_info:
                app_info = run_async(mcp_client.get_app(server_url=server_url))

            has_unauth_access = app_info.unauthenticatedAccess is True or (
                app_info.appServerInfo
                and app_info.appServerInfo.unauthenticatedAccess is True
            )

            if not has_unauth_access:
                console.print(
                    Panel(
                        f"[bold red]❌ ChatGPT Requires Unauthenticated Access[/bold red]\n\n"
                        f"This server requires authentication, but ChatGPT only supports:\n"
                        f"  • Unauthenticated (public) servers\n"
                        f"  • OAuth (not yet supported by mcp-agent install)\n\n"
                        f"[bold]Options:[/bold]\n\n"
                        f"1. Enable unauthenticated access for this server:\n"
                        f"   [cyan]mcp-agent cloud apps update --id {app_info.appId} --unauthenticated-access true[/cyan]\n\n"
                        f"2. Use a client that supports authentication:\n"
                        f"   [green]• Claude Code:[/green]    mcp-agent install {server_url} --client claude_code\n"
                        f"   [green]• Claude Desktop:[/green] mcp-agent install {server_url} --client claude_desktop\n"
                        f"   [green]• Cursor:[/green]         mcp-agent install {server_url} --client cursor\n"
                        f"   [green]• VSCode:[/green]         mcp-agent install {server_url} --client vscode",
                        title="Installation Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            print_info(f"Warning: Could not verify unauthenticated access: {e}")
            print_info(
                "Proceeding with installation, but ChatGPT may not be able to connect."
            )

        console.print(
            Panel(
                f"[bold]ChatGPT Setup Instructions[/bold]\n\n"
                f"1. Open ChatGPT settings\n"
                f"2. Navigate to the Apps & Connectors section\n"
                f"3. Enable developer mode under advanced settings\n"
                f"4. Select create on the top right corner of the panel\n"
                f"5. Add a new server:\n"
                f"   • URL: [cyan]{server_url}[/cyan]\n"
                f"   • Transport: [cyan]sse[/cyan]\n\n"
                f"[dim]Note: This server has unauthenticated access enabled.[/dim]",
                title="ChatGPT Configuration",
                border_style="green",
            )
        )
        return

    server_name = name or _server_hostname(server_url, app_name)

    transport = "sse" if server_url.rstrip("/").endswith("/sse") else "http"

    if client_lc == "claude_code":
        if dry_run:
            console.print("\n[bold yellow]DRY RUN - Would run:[/bold yellow]")
            console.print(
                f"claude mcp add {server_name} {server_url} -t {transport} -H 'Authorization: Bearer <api-key>' -s user"
            )
            return

        try:
            cmd = [
                "claude",
                "mcp",
                "add",
                server_name,
                server_url,
                "-t",
                transport,
                "-H",
                f"Authorization: Bearer {effective_api_key}",
                "-s",
                "user",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30
            )
            print_success(f"Server '{server_name}' installed to Claude Code")
            console.print(result.stdout)
            return
        except subprocess.CalledProcessError as e:
            raise CLIError(f"Failed to add server to Claude Code: {e.stderr}") from e
        except FileNotFoundError:
            raise CLIError(
                "Claude Code CLI not found. Make sure 'claude' command is available in your PATH.\n"
                "Install from: https://docs.claude.com/en/docs/claude-code"
            )

    if dry_run:
        print_info("[bold yellow]DRY RUN - No files will be written[/bold yellow]")

    client_config = CLIENT_CONFIGS[client_lc]
    config_path = client_config["path"]()

    is_vscode = client_lc == "vscode"
    is_claude_desktop = client_lc == "claude_desktop"
    is_cursor = client_lc == "cursor"

    existing_config = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
            if is_claude_desktop or is_cursor:
                servers = existing_config.get("mcpServers", {})
            elif is_vscode:
                servers = existing_config.get("servers", {})
            else:
                servers = existing_config.get("mcp", {}).get("servers", {})

            if server_name in servers and not force:
                raise CLIError(
                    f"Server '{server_name}' already exists in {config_path}. Use --force to overwrite."
                )
        except json.JSONDecodeError as e:
            raise CLIError(
                f"Failed to parse existing config at {config_path}: {e}"
            ) from e

    server_config = _build_server_config(
        server_url,
        transport,
        for_claude_desktop=is_claude_desktop,
        for_vscode=is_vscode,
        api_key=effective_api_key,
    )

    if is_claude_desktop or is_cursor:
        format_type = "mcpServers"
    elif is_vscode:
        format_type = "vscode"
    else:
        format_type = "mcp"

    merged_config = _merge_mcp_json(
        existing_config, server_name, server_config, format_type
    )

    if dry_run:
        console.print("\n[bold]Would write to:[/bold]", config_path)
        console.print("\n[bold]Config:[/bold]")
        console.print_json(data=_redact_secrets(merged_config))
    else:
        try:
            _write_json(config_path, merged_config)
            print_success(f"Server '{server_name}' installed to {config_path}")
        except Exception as e:
            raise CLIError(f"Failed to write config file: {e}") from e

        if is_claude_desktop:
            auth_note = (
                "[bold]Note:[/bold] Claude Desktop uses [cyan]mcp-remote[/cyan] to connect to HTTP/SSE servers\n"
                "[dim]API key embedded in config. Restart Claude Desktop to load the server.[/dim]"
            )
        elif is_vscode:
            auth_note = (
                f"[bold]Note:[/bold] VSCode format uses [cyan]type: {transport}[/cyan]\n"
                f"[dim]API key embedded. Restart VSCode to load the server.[/dim]"
            )
        elif is_cursor:
            auth_note = (
                f"[bold]Note:[/bold] Cursor format uses [cyan]transport: {transport}[/cyan]\n"
                f"[dim]API key embedded. Restart Cursor to load the server.[/dim]"
            )
        else:
            auth_note = (
                "[bold]Authentication:[/bold] API key embedded in config\n"
                "[dim]To update the key, re-run install with --force[/dim]"
            )

        console.print(
            Panel(
                f"[bold green]✅ Installation Complete![/bold green]\n\n"
                f"Server: [cyan]{server_name}[/cyan]\n"
                f"URL: [cyan]{server_url}[/cyan]\n"
                f"Client: [cyan]{client_config['description']}[/cyan]\n"
                f"Config: [cyan]{config_path}[/cyan]\n\n"
                f"{auth_note}",
                title="MCP Server Installed",
                border_style="green",
            )
        )
