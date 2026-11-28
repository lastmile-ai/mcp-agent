"""stdio serve must run MCPApp.cleanup after a normal transport return."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_agent.cli.commands.serve import app as serve_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _settings() -> SimpleNamespace:
    return SimpleNamespace(mcp=None)


def test_stdio_serve_calls_cleanup_after_normal_eof(
    tmp_path, runner: CliRunner
) -> None:
    script = tmp_path / "app.py"
    script.write_text("# placeholder script for path detection\n", encoding="utf-8")

    app_obj = MagicMock()
    app_obj.name = "eof-cleanup"
    app_obj.initialize = AsyncMock()
    app_obj.cleanup = AsyncMock()
    app_obj.workflows = {}
    app_obj.agents = {}

    mcp = MagicMock()
    mcp.run_stdio_async = AsyncMock()

    with (
        patch("mcp_agent.cli.commands.serve.load_user_app", return_value=app_obj),
        patch(
            "mcp_agent.cli.commands.serve.create_mcp_server_for_app", return_value=mcp
        ),
        patch("mcp_agent.cli.commands.serve.get_settings", return_value=_settings()),
        patch("mcp_agent.cli.commands.serve.signal.signal"),
    ):
        result = runner.invoke(
            serve_app,
            ["--script", str(script), "--transport", "stdio"],
        )

    assert result.exception is None, result.output
    assert result.exit_code == 0, result.output
    app_obj.initialize.assert_awaited_once()
    mcp.run_stdio_async.assert_awaited_once()
    app_obj.cleanup.assert_awaited_once()
    assert app_obj.initialize.await_args is not None
    assert mcp.run_stdio_async.await_args is not None
    assert app_obj.cleanup.await_args is not None
    assert app_obj.initialize.await_args.args == ()
    # cleanup must run after the stdio transport returns
    assert app_obj.cleanup.await_count == 1
    assert mcp.run_stdio_async.await_count == 1


def test_stdio_serve_calls_cleanup_after_broken_pipe(
    tmp_path, runner: CliRunner
) -> None:
    script = tmp_path / "app.py"
    script.write_text("# placeholder script for path detection\n", encoding="utf-8")

    app_obj = MagicMock()
    app_obj.name = "eof-cleanup"
    app_obj.initialize = AsyncMock()
    app_obj.cleanup = AsyncMock()
    app_obj.workflows = {}
    app_obj.agents = {}

    mcp = MagicMock()
    mcp.run_stdio_async = AsyncMock(side_effect=Exception("Broken pipe"))

    with (
        patch("mcp_agent.cli.commands.serve.load_user_app", return_value=app_obj),
        patch(
            "mcp_agent.cli.commands.serve.create_mcp_server_for_app", return_value=mcp
        ),
        patch("mcp_agent.cli.commands.serve.get_settings", return_value=_settings()),
        patch("mcp_agent.cli.commands.serve.signal.signal"),
    ):
        result = runner.invoke(
            serve_app,
            ["--script", str(script), "--transport", "stdio"],
        )

    assert result.exception is None, result.output
    assert result.exit_code == 0, result.output
    app_obj.cleanup.assert_awaited_once()
