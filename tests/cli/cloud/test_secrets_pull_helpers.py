from pathlib import Path

import pytest

from mcp_agent.cli.cloud.commands.secrets.main import (
    _format_env_value,
    _load_env_file_values,
    _write_env_file,
)


def test_format_env_value_quotes_special_characters():
    assert _format_env_value("plain") == "plain"
    assert _format_env_value("token with spaces") == '"token with spaces"'
    assert _format_env_value('value"with"quotes') == '"value\\"with\\"quotes"'
    assert _format_env_value("multi\nline") == '"multi\\nline"'


def test_write_env_file(tmp_path: Path):
    values = {"B_KEY": "b value", "A_KEY": "alpha"}
    env_path = tmp_path / ".env.mcp-cloud"
    _write_env_file(env_path, values)

    contents = env_path.read_text(encoding="utf-8").splitlines()
    assert contents == ["A_KEY=alpha", 'B_KEY="b value"']


def test_load_env_file_values(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text('A_KEY="alpha value"\nB_KEY=beta\n', encoding="utf-8")
    values = _load_env_file_values(env_path)
    assert values == {"A_KEY": "alpha value", "B_KEY": "beta"}


def test_load_env_file_values_errors_for_missing_entries(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    with pytest.raises(Exception):
        _load_env_file_values(env_path)
