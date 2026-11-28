"""stdio serve must redirect shared consoles to stderr before app init."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_agent.cli.commands.serve import app as serve_app
from mcp_agent.console import (
    console,
    error_console,
    log_console,
    server_console,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def restore_console_files():
    originals = {
        "console": console.file,
        "error_console": error_console.file,
        "log_console": log_console.file,
        "server_console": server_console.file,
    }
    try:
        yield
    finally:
        console.file = originals["console"]
        error_console.file = originals["error_console"]
        log_console.file = originals["log_console"]
        server_console.file = originals["server_console"]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(mcp=None)


def test_stdio_serve_redirects_consoles_before_initialize(
    tmp_path, runner: CliRunner, restore_console_files
) -> None:
    script = tmp_path / "app.py"
    script.write_text("# placeholder script for path detection\n", encoding="utf-8")

    app_obj = MagicMock()
    app_obj.name = "stdio-control"
    order: list[str] = []

    def _redirect() -> None:
        order.append("redirect")

    async def _initialize() -> None:
        order.append("initialize")

    app_obj.initialize = AsyncMock(side_effect=_initialize)
    app_obj.workflows = {}
    app_obj.agents = {}

    mcp = MagicMock()
    mcp.run_stdio_async = AsyncMock()

    # serve() imports the helper inside _run(), so patch the module symbol.
    with (
        patch(
            "mcp_agent.console.redirect_console_output_to_stderr",
            side_effect=_redirect,
        ) as redirect,
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
    redirect.assert_called_once()
    assert order == ["redirect", "initialize"]


def test_http_serve_does_not_redirect_shared_consoles(
    tmp_path, runner: CliRunner, restore_console_files
) -> None:
    script = tmp_path / "app.py"
    script.write_text("# placeholder script for path detection\n", encoding="utf-8")

    original = console.file
    app_obj = MagicMock()
    app_obj.name = "http-control"
    app_obj.initialize = AsyncMock()
    app_obj.workflows = {}
    app_obj.agents = {}

    # Abort after the app is loaded by failing server-info rendering.
    # The stdio redirect happens before load; HTTP must not have run it.
    with (
        patch("mcp_agent.cli.commands.serve.load_user_app", return_value=app_obj),
        patch(
            "mcp_agent.cli.commands.serve.create_mcp_server_for_app",
            return_value=MagicMock(),
        ),
        patch("mcp_agent.cli.commands.serve.get_settings", return_value=_settings()),
        patch("mcp_agent.cli.commands.serve.signal.signal"),
        patch("mcp_agent.cli.commands.serve.Panel", side_effect=RuntimeError("stop")),
    ):
        runner.invoke(
            serve_app,
            ["--script", str(script), "--transport", "http", "--port", "0"],
        )

    assert console.file is original
    app_obj.initialize.assert_awaited_once()
