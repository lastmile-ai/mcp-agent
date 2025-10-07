"""Tests for the version check helper."""

import importlib
import os
from typing import List

import pytest


@pytest.fixture()
def version_check(monkeypatch):
    """Reload the module to reset globals between tests."""
    from mcp_agent.cli.utils import version_check as vc_mod

    vc = importlib.reload(vc_mod)
    monkeypatch.delenv("MCP_AGENT_DISABLE_VERSION_CHECK", raising=False)
    monkeypatch.delenv("MCP_AGENT_VERSION_CHECKED", raising=False)
    vc._version_check_started = False  # type: ignore[attr-defined]
    vc._version_check_message = None  # type: ignore[attr-defined]
    vc._version_check_event.clear()  # type: ignore[attr-defined]

    registrations: List = []

    def fake_register(func):
        registrations.append(func)
        return func

    monkeypatch.setattr(vc.atexit, "register", fake_register, raising=False)
    vc._test_registrations = registrations  # type: ignore[attr-defined]
    return vc


def test_version_check_respects_disable_env(monkeypatch, version_check):
    monkeypatch.setenv("MCP_AGENT_DISABLE_VERSION_CHECK", "true")
    calls: List[int] = []
    monkeypatch.setattr(
        version_check,
        "_spawn_version_check_thread",
        lambda: calls.append(1),
        raising=False,
    )

    version_check.maybe_warn_newer_version()

    assert calls == []
    assert "MCP_AGENT_VERSION_CHECKED" not in os.environ
    assert version_check._test_registrations == []  # type: ignore[attr-defined]


def test_version_check_runs_once(monkeypatch, version_check):
    calls: List[int] = []
    monkeypatch.setattr(
        version_check,
        "_spawn_version_check_thread",
        lambda: calls.append(1),
        raising=False,
    )

    version_check.maybe_warn_newer_version()
    version_check.maybe_warn_newer_version()

    assert calls == [1]
    assert os.environ.get("MCP_AGENT_VERSION_CHECKED") == "1"
    # atexit should be registered exactly once
    assert len(version_check._test_registrations) == 1  # type: ignore[attr-defined]


def test_version_check_flushes_message(monkeypatch, version_check):
    monkeypatch.setattr(
        version_check,
        "_get_installed_version",
        lambda: "0.1.0",
        raising=False,
    )
    monkeypatch.setattr(
        version_check,
        "_fetch_latest_version",
        lambda timeout_seconds=5.0: "0.2.0",
        raising=False,
    )

    captured = []

    monkeypatch.setattr(
        version_check,
        "print_info",
        lambda message, console_output=True: captured.append(message),
        raising=False,
    )

    # Run worker synchronously for the test
    monkeypatch.setattr(
        version_check,
        "_spawn_version_check_thread",
        version_check._run_version_check,
        raising=False,
    )

    version_check.maybe_warn_newer_version()

    # Simulate interpreter exit
    registration = version_check._test_registrations[0]  # type: ignore[attr-defined]
    registration()

    assert captured
    assert "0.1.0" in captured[0]
