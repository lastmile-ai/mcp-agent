"""Secrets subcommands for mcp-agent cloud."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

import typer
import yaml
from dotenv import dotenv_values
from rich.table import Table
from mcp_agent.cli.auth import load_api_key_credentials
from mcp_agent.cli.cloud.commands.utils import (
    get_app_defaults_from_config,
    resolve_server,
)
from mcp_agent.cli.config import settings
from mcp_agent.cli.core.constants import (
    MCP_CONFIG_FILENAME,
)
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.mcp_app.api_client import MCPApp, MCPAppClient
from mcp_agent.cli.secrets import SecretType, SecretsClient
from mcp_agent.cli.utils.ux import console, print_error, print_info, print_success

app = typer.Typer(
    help="Manage cloud secrets for MCP apps",
    no_args_is_help=True,
)


def _format_env_value(value: str) -> str:
    if value is None:
        return ""
    needs_quotes = bool(re.search(r"[^\w@./-]", value))
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace('"', '\\"')
    )
    return f'"{escaped}"' if needs_quotes else escaped


def _write_env_file(path: Path, values: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for key in sorted(values):
            handle.write(f"{key}={_format_env_value(values[key])}\n")


def _confirm_overwrite(target: Path, force: bool, label: str) -> None:
    if target.exists() and not force:
        overwrite = typer.confirm(
            f"{target} already exists. Overwrite {label}?", default=False
        )
        if not overwrite:
            print_info("Aborted.")
            raise typer.Exit(0)


def _load_env_file_values(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise CLIError(f"Env file not found: {path}")
    parsed = dotenv_values(path)
    values: Dict[str, str] = {}
    for key, value in parsed.items():
        if key and value is not None:
            values[key] = str(value)
    if not values:
        raise CLIError(f"No valid entries found in {path}")
    return values


def _ensure_api_key(api_key_option: Optional[str]) -> str:
    effective_key = api_key_option or settings.API_KEY or load_api_key_credentials()
    if not effective_key:
        raise CLIError(
            "Must be logged in. Run 'mcp-agent login', set MCP_API_KEY, or pass --api-key."
        )
    return effective_key


def _make_secrets_client(api_url: Optional[str], api_key: str) -> SecretsClient:
    return SecretsClient(
        api_url=api_url or settings.API_BASE_URL,
        api_key=api_key,
    )


def _resolve_app(
    app_identifier: Optional[str],
    config_dir: Path,
    api_url: Optional[str],
    api_key: str,
) -> MCPApp:
    """Resolve an MCP app from argument or config defaults."""
    client = MCPAppClient(
        api_url=api_url or settings.API_BASE_URL,
        api_key=api_key,
    )

    config_file = (config_dir / MCP_CONFIG_FILENAME) if config_dir else None
    if app_identifier:
        server = resolve_server(client, app_identifier)
        if isinstance(server, MCPApp):
            return server
        if server.app:
            return server.app
        raise CLIError(
            f"Could not resolve MCP app for identifier '{app_identifier}'. Provide an app name or ID."
        )

    default_name, _ = get_app_defaults_from_config(config_file)
    if default_name:
        app_obj = run_async(client.get_app_by_name(default_name))
        if app_obj:
            return app_obj

    raise CLIError(
        "Unable to determine which app to target. Provide an app name/id or run the command within a project directory."
    )


def _env_secret_prefix(app_id: str) -> str:
    return f"apps/{app_id}/env/"


def _load_existing_handles(client: SecretsClient, app_id: str) -> Dict[str, str]:
    prefix = _env_secret_prefix(app_id)
    secrets = run_async(client.list_secrets(name_filter=prefix))
    handles: Dict[str, str] = {}
    for entry in secrets:
        handle = entry.get("secretId") or entry.get("secret_id")
        name = entry.get("name")
        if not handle or not name or not name.startswith(prefix):
            continue
        key = name[len(prefix) :]
        handles[key] = handle
    return handles


@app.command("list")
def list_secrets(
    app_name: Optional[str] = typer.Argument(
        None, help="App name, ID, or server URL. Defaults to project config."
    ),
    config_dir: Path = typer.Option(
        Path("."),
        "--config-dir",
        "-c",
        help="Path to directory containing mcp_agent.config.yaml.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
    ),
    app_option: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        help="App name, ID, or server URL (overrides positional argument).",
    ),
) -> None:
    """List environment secrets associated with an app."""
    effective_key = _ensure_api_key(api_key)
    target_app = app_option or app_name
    app_obj = _resolve_app(target_app, config_dir, api_url, effective_key)
    client = _make_secrets_client(api_url, effective_key)

    handles = _load_existing_handles(client, app_obj.appId)
    if not handles:
        print_info(f"No secrets found for app '{app_obj.name or app_obj.appId}'.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Key", style="cyan")
    table.add_column("Secret Handle", style="green")

    for key, handle in sorted(handles.items()):
        masked = handle[:8] + "…" + handle[-6:] if len(handle) > 14 else handle
        table.add_row(key, masked)

    console.print(table)


@app.command("add")
def add_secret(
    key: Optional[str] = typer.Argument(
        None, help="Environment variable to store as a secret"
    ),
    value: Optional[str] = typer.Argument(None, help="Secret value to store"),
    app_name_arg: Optional[str] = typer.Argument(
        None, help="App name, ID, or server URL. Defaults to project config."
    ),
    config_dir: Path = typer.Option(
        Path("."),
        "--config-dir",
        "-c",
        help="Path to directory containing mcp_agent.config.yaml.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
    ),
    app_name_option: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        help="App name, ID, or server URL (recommended when using --from-env-file).",
    ),
    env_file: Optional[Path] = typer.Option(
        None,
        "--from-env-file",
        help="Path to a dotenv file to bulk add secrets.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Create or update environment secret(s)."""
    if env_file and (key or value):
        raise CLIError(
            "Specify either --from-env-file or KEY/VALUE arguments (use --app to set the target app)."
        )
    if not env_file and (not key or value is None):
        raise CLIError("KEY and VALUE are required unless --from-env-file is provided.")

    effective_key = _ensure_api_key(api_key)
    target_app = app_name_option or app_name_arg
    if env_file and not target_app:
        raise CLIError("Provide an app via --app when using --from-env-file.")

    app_obj = _resolve_app(target_app, config_dir, api_url, effective_key)
    client = _make_secrets_client(api_url, effective_key)

    handles = _load_existing_handles(client, app_obj.appId)
    items: Dict[str, str] = {}
    if env_file:
        items = _load_env_file_values(env_file)
    else:
        items[key] = value  # type: ignore[index]

    for item_key, item_value in items.items():
        if not item_value:
            raise CLIError(f"Secret value must be non-empty for {item_key}.")
        handle = handles.get(item_key)
        if handle:
            run_async(client.set_secret_value(handle, item_value))
            print_success(f"Updated secret for {item_key}.")
        else:
            secret_name = f"{_env_secret_prefix(app_obj.appId)}{item_key}"
            handle = run_async(
                client.create_secret(
                    name=secret_name,
                    secret_type=SecretType.DEVELOPER,
                    value=item_value,
                )
            )
            print_success(f"Created secret for {item_key}: {handle}")


@app.command("remove")
def remove_secret(
    key: str = typer.Argument(..., help="Environment variable to delete"),
    app_name: Optional[str] = typer.Argument(
        None, help="App name, ID, or server URL. Defaults to project config."
    ),
    config_dir: Path = typer.Option(
        Path("."),
        "--config-dir",
        "-c",
        help="Path to directory containing mcp_agent.config.yaml.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
    ),
    app_name_option: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        help="App name, ID, or server URL (overrides positional argument).",
    ),
) -> None:
    """Delete a stored environment secret."""
    effective_key = _ensure_api_key(api_key)
    target_app = app_name_option or app_name
    app_obj = _resolve_app(target_app, config_dir, api_url, effective_key)
    client = _make_secrets_client(api_url, effective_key)

    handles = _load_existing_handles(client, app_obj.appId)
    handle = handles.get(key)
    if not handle:
        print_error(f"No secret stored for {key}.")
        raise typer.Exit(1)

    run_async(client.delete_secret(handle))
    print_success(f"Removed secret for {key}.")


@app.command("pull")
def pull_secrets(
    app_name: Optional[str] = typer.Argument(
        None, help="App name, ID, or server URL. Defaults to project config."
    ),
    config_dir: Path = typer.Option(
        Path("."),
        "--config-dir",
        "-c",
        help="Path to directory containing mcp_agent.config.yaml.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    format: str = typer.Option(
        "env",
        "--format",
        "-f",
        help="Output format: 'env' writes a dotenv file, 'yaml' writes a secrets YAML.",
        case_sensitive=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination file (defaults to .env.mcp-cloud for env format, mcp_agent.cloud.secrets.yaml for yaml format).",
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite output file without confirmation."
    ),
    api_url: Optional[str] = typer.Option(
        settings.API_BASE_URL,
        "--api-url",
        help="API base URL. Defaults to MCP_API_BASE_URL environment variable.",
    ),
    api_key: Optional[str] = typer.Option(
        settings.API_KEY,
        "--api-key",
        help="API key for authentication. Defaults to MCP_API_KEY environment variable.",
    ),
    app_name_option: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        help="App name, ID, or server URL (overrides positional argument).",
    ),
) -> None:
    """Fetch secret values and write them to a local YAML file."""
    effective_key = _ensure_api_key(api_key)
    target_app = app_name_option or app_name
    app_obj = _resolve_app(target_app, config_dir, api_url, effective_key)
    client = _make_secrets_client(api_url, effective_key)

    handles = _load_existing_handles(client, app_obj.appId)
    if not handles:
        print_info(f"No secrets found for app '{app_obj.name or app_obj.appId}'.")
        return

    resolved: Dict[str, str] = {}
    for key, handle in handles.items():
        value = run_async(client.get_secret_value(handle))
        resolved[key] = value

    format = format.lower()
    if format not in {"env", "yaml"}:
        raise CLIError("Format must be either 'env' or 'yaml'.")
    default_path = (
        Path(".env.mcp-cloud")
        if format == "env"
        else Path("mcp_agent.cloud.secrets.yaml")
    )
    dest = output or default_path

    label = "dotenv file" if format == "env" else "YAML secrets file"
    _confirm_overwrite(dest, force, label)

    dest.parent.mkdir(parents=True, exist_ok=True)
    if format == "env":
        _write_env_file(dest, resolved)
    else:
        with open(dest, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                {"env": resolved},
                handle,
                default_flow_style=False,
                sort_keys=True,
            )

    print_success(f"Pulled {len(resolved)} secret(s) into {dest}.")
