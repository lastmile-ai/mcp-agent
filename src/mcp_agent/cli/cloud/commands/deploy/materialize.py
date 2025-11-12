"""Helpers for materializing deployment artifacts prior to bundling."""

from __future__ import annotations

import copy
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import typer
import yaml
from mcp_agent.cli.core.constants import MCP_DEPLOYED_CONFIG_FILENAME
from mcp_agent.cli.core.utils import run_async
from mcp_agent.cli.exceptions import CLIError
from mcp_agent.cli.secrets import SecretType, SecretsClient
from mcp_agent.cli.secrets.yaml_tags import (
    dump_yaml_with_secrets,
    load_yaml_with_secrets,
)
from mcp_agent.config import Settings, get_settings


@dataclass(slots=True)
class EnvSpec:
    """Normalized environment specification."""

    key: str
    fallback: str | None = None

    @property
    def secret_name(self) -> str:
        return self.key


def _normalize_env_specs(settings: Settings) -> list[EnvSpec]:
    """Coerce the flexible env syntax into ordered EnvSpec rows."""
    specs: list[EnvSpec] = []
    for key, fallback in settings.iter_env_specs():
        specs.append(EnvSpec(key=key, fallback=fallback))
    return specs


def _secret_name_for_env(app_id: str, key: str) -> str:
    return f"apps/{app_id}/env/{key}"


def _load_deployed_secrets(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    loaded = load_yaml_with_secrets(raw)
    return loaded or {}


def _extract_existing_env_handles(data: dict) -> dict[str, str]:
    env_section = data.get("env")
    handles: dict[str, str] = {}
    if isinstance(env_section, list):
        for item in env_section:
            if isinstance(item, dict) and len(item) == 1:
                key, value = next(iter(item.items()))
                if isinstance(key, str) and isinstance(value, str):
                    handles[key] = value
    return handles


def _persist_deployed_secrets(path: Path, data: dict) -> None:
    content = dump_yaml_with_secrets(data)
    path.write_text(content, encoding="utf-8")


def _load_raw_config(config_file: Path) -> dict:
    if not config_file.exists():
        return {}
    try:
        return yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_deployed_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)


_REMOVE = object()


def _redact_config_values(
    current: object, secrets_overlay: object, raw_config: object
) -> object:
    """Return `current` with any nodes present in `secrets_overlay` removed or replaced with `raw_config` values."""

    if secrets_overlay is None:
        return current

    if isinstance(secrets_overlay, dict) and isinstance(current, dict):
        result: dict = copy.deepcopy(current)
        raw_dict = raw_config if isinstance(raw_config, dict) else {}
        for key, overlay_value in secrets_overlay.items():
            if key not in result:
                continue
            base_value = raw_dict.get(key)
            replacement = _redact_config_values(result[key], overlay_value, base_value)
            if replacement is _REMOVE:
                if base_value is not None:
                    result[key] = copy.deepcopy(base_value)
                else:
                    result.pop(key, None)
            else:
                result[key] = replacement

        if not result:
            if raw_dict:
                return copy.deepcopy(raw_dict)
            return _REMOVE
        return result

    if isinstance(secrets_overlay, list) and isinstance(current, list):
        raw_list = raw_config if isinstance(raw_config, list) else []
        result_list = []
        max_len = len(current)
        for idx in range(max_len):
            item = current[idx]
            overlay_item = secrets_overlay[idx] if idx < len(secrets_overlay) else None
            base_item = raw_list[idx] if idx < len(raw_list) else None
            if overlay_item is None:
                result_list.append(item)
                continue
            replacement = _redact_config_values(item, overlay_item, base_item)
            if replacement is _REMOVE:
                if base_item is not None:
                    result_list.append(copy.deepcopy(base_item))
            else:
                result_list.append(replacement)
        return result_list

    # Scalar secret entry – fall back to raw config if present, otherwise drop.
    if raw_config is not None:
        return copy.deepcopy(raw_config)
    return _REMOVE


def materialize_deployment_artifacts(
    *,
    config_dir: Path,
    app_id: str,
    config_file: Path,
    deployed_secrets_path: Path,
    secrets_client: SecretsClient,
    non_interactive: bool,
) -> tuple[Path, Path]:
    """Generate deployment-ready config and secrets files.

    Returns the paths to the deployed config and secrets files.
    """

    if not config_file.exists():
        raise CLIError(f"Configuration file not found: {config_file}")

    settings = _load_settings_from_app(config_dir)
    settings_source = "main.py MCPApp"
    if settings is None:
        settings_source = str(config_file)
        try:
            settings = get_settings(config_path=str(config_file), set_global=False)
        except Exception as exc:
            typer.secho(
                f"Skipping deployment materialization due to config error: {exc}",
                fg=typer.colors.YELLOW,
            )
            if not deployed_secrets_path.exists():
                deployed_secrets_path.write_text(
                    yaml.safe_dump({}, default_flow_style=False, sort_keys=False),
                    encoding="utf-8",
                )
            return config_file, deployed_secrets_path

    typer.secho(
        f"Materializing config from {settings_source}",
        fg=typer.colors.BLUE,
    )

    env_specs = _normalize_env_specs(settings)
    secrets_data = _load_deployed_secrets(deployed_secrets_path)

    materialized_config = settings.model_dump(
        mode="json",
        exclude_none=True,
        exclude_unset=True,
        exclude_defaults=True,
    )
    raw_config = _load_raw_config(config_file)
    sanitized_config = _redact_config_values(
        copy.deepcopy(materialized_config),
        copy.deepcopy(secrets_data),
        raw_config,
    )
    deployed_config_path = config_dir / MCP_DEPLOYED_CONFIG_FILENAME
    _write_deployed_config(deployed_config_path, sanitized_config or {})

    if not env_specs:
        # Nothing further to do; ensure secrets file exists if previously created
        if not deployed_secrets_path.exists():
            deployed_secrets_path.write_text(
                yaml.safe_dump({}, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
        return deployed_config_path, deployed_secrets_path

    secrets_path_parent = deployed_secrets_path.parent
    secrets_path_parent.mkdir(parents=True, exist_ok=True)
    existing_env_handles = _extract_existing_env_handles(secrets_data)

    normalized_env_entries: list[dict[str, str]] = []

    for spec in env_specs:
        value = os.environ.get(spec.key)
        fallback_used = False

        if value is None:
            if spec.fallback is not None:
                value = str(spec.fallback)
                fallback_used = True
            elif non_interactive:
                raise CLIError(
                    f"Environment variable '{spec.key}' is required but not set. "
                    "Provide it via the environment, configure a fallback, or rerun without --non-interactive."
                )
            else:
                prompt_text = f"Enter value for environment variable '{spec.key}'"
                value = typer.prompt(prompt_text, hide_input=True)
                fallback_used = True

        if value is None or value == "":
            raise CLIError(
                f"Environment variable '{spec.key}' resolved to an empty value. "
                "Provide a non-empty value via the environment or configuration."
            )

        handle = existing_env_handles.get(spec.key)
        secret_name = _secret_name_for_env(app_id, spec.key)

        handle_reused = False
        if handle:
            try:
                success = run_async(secrets_client.set_secret_value(handle, value))
                if success:
                    handle_reused = True
                else:
                    typer.secho(
                        f"Existing secret handle for '{spec.key}' is invalid; creating a new secret.",
                        fg=typer.colors.YELLOW,
                    )
                    handle = None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    typer.secho(
                        f"Secret handle for '{spec.key}' no longer exists; creating a new secret.",
                        fg=typer.colors.YELLOW,
                    )
                    handle = None
                else:
                    raise
            except Exception as exc:
                typer.secho(
                    f"Failed to reuse secret handle for '{spec.key}': {exc}. Creating a new secret.",
                    fg=typer.colors.YELLOW,
                )
                handle = None

        if not handle:
            handle = run_async(
                secrets_client.create_secret(
                    name=secret_name,
                    secret_type=SecretType.DEVELOPER,
                    value=value,
                )
            )
            handle_reused = False

        if not handle_reused:
            existing_env_handles[spec.key] = handle

        normalized_env_entries.append({spec.key: handle})

        if fallback_used and spec.fallback is None:
            # Inform the user their manual input won't be persisted outside the secret.
            typer.secho(
                f"Captured value for '{spec.key}' during deployment; it will be stored as a secret.",
                fg=typer.colors.BLUE,
            )

    secrets_data["env"] = normalized_env_entries
    _persist_deployed_secrets(deployed_secrets_path, secrets_data)

    return deployed_config_path, deployed_secrets_path


def _load_settings_from_app(config_dir: Path) -> Settings | None:
    module_name = "main"
    project_root = config_dir.resolve()
    module_path = str(project_root)
    added_path = False
    try:
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
            added_path = True

        if module_name in sys.modules:
            del sys.modules[module_name]

        module = importlib.import_module(module_name)
        module_file = Path(getattr(module, "__file__", "")).resolve()
        if not module_file or project_root not in module_file.parents:
            typer.secho(
                f"Module 'main' resolved outside project directory ({module_file}); skipping MCPApp load.",
                fg=typer.colors.YELLOW,
            )
            return None
        from mcp_agent.app import MCPApp

        apps = [
            value for value in module.__dict__.values() if isinstance(value, MCPApp)
        ]

        if len(apps) != 1:
            if not apps:
                typer.secho(
                    f"Module '{module_name}' does not export an MCPApp instance.",
                    fg=typer.colors.YELLOW,
                )
            else:
                typer.secho(
                    f"Module '{module_name}' exports multiple MCPApp instances.",
                    fg=typer.colors.YELLOW,
                )
            return None

        return apps[0].config
    except ModuleNotFoundError:
        typer.secho(
            "Unable to import 'main' module while materializing config.",
            fg=typer.colors.YELLOW,
        )
    except Exception as exc:
        typer.secho(
            f"Failed to load MCPApp config from 'main': {exc}",
            fg=typer.colors.YELLOW,
        )
    finally:
        if added_path and module_path in sys.path:
            try:
                sys.path.remove(module_path)
            except ValueError:
                pass
    return None
