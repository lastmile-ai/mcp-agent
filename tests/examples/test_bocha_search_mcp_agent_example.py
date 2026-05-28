from pathlib import Path

import yaml


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
