from pathlib import Path
import re

import yaml
import pytest


EXAMPLE_DIR = Path("examples/usecases/bocha_search_mcp_agent")


def test_bocha_example_config_uses_runtime_env_without_secret():
    config_path = EXAMPLE_DIR / "mcp_agent.config.yaml"

    config_text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)
    bocha = config["mcp"]["servers"]["bocha"]

    assert bocha["command"] == "uv"
    assert "env" not in bocha
    assert "sk-" not in config_text


def test_bocha_example_raises_when_search_tool_returns_api_error():
    from examples.usecases.bocha_search_mcp_agent.main import raise_for_bocha_error

    class Text:
        text = "Bocha Web Search API HTTP error occurred: 401 - Invalid API KEY"

    class Result:
        content = [Text()]

    try:
        raise_for_bocha_error(Result())
    except RuntimeError as exc:
        assert "Bocha search failed" in str(exc)
    else:
        raise AssertionError("Expected Bocha API errors to fail the smoke test")


def test_bocha_example_reads_server_config_from_process_env(monkeypatch):
    from examples.usecases.bocha_search_mcp_agent.main import (
        bocha_server_config_from_process,
    )

    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("BOCHA_SEARCH_MCP_DIR", "D:/bocha-search-mcp")

    args, env = bocha_server_config_from_process()

    assert args == [
        "--directory",
        str(Path("D:/bocha-search-mcp")),
        "run",
        "bocha-search-mcp",
    ]
    assert env == {"BOCHA_API_KEY": "test-key"}


def test_bocha_example_requires_api_key(monkeypatch, tmp_path):
    from examples.usecases.bocha_search_mcp_agent.main import (
        bocha_server_config_from_process,
    )

    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    monkeypatch.setenv("BOCHA_SEARCH_MCP_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="BOCHA_API_KEY"):
        bocha_server_config_from_process()


def test_bocha_example_requires_server_dir(monkeypatch):
    from examples.usecases.bocha_search_mcp_agent.main import (
        bocha_server_config_from_process,
    )

    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.delenv("BOCHA_SEARCH_MCP_DIR", raising=False)

    with pytest.raises(RuntimeError, match="BOCHA_SEARCH_MCP_DIR"):
        bocha_server_config_from_process()


def test_bocha_example_rejects_invalid_server_dir(monkeypatch, tmp_path):
    from examples.usecases.bocha_search_mcp_agent.main import (
        bocha_server_config_from_process,
    )

    missing_dir = tmp_path / "missing"
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("BOCHA_SEARCH_MCP_DIR", str(missing_dir))

    with pytest.raises(RuntimeError, match=re.escape(str(missing_dir))):
        bocha_server_config_from_process()


def test_bocha_example_raises_when_search_tool_missing():
    from examples.usecases.bocha_search_mcp_agent.main import find_bocha_search_tool

    with pytest.raises(RuntimeError, match="available tools"):
        find_bocha_search_tool(["bocha_bocha_ai_search"])
