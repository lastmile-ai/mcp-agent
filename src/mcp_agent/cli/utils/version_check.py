"""Best-effort PyPI version check for mcp-agent.

- Contacts PyPI JSON API for the latest published version
- Compares with the installed version
- Prints an info hint if an update is available
- Executes in a background thread so startup is never blocked for more than
  the HTTP timeout (5 seconds by default)
"""

from __future__ import annotations

import atexit
import os
import threading
from typing import Optional

from mcp_agent.cli.utils.ux import print_info

_version_check_lock = threading.Lock()
_version_check_started = False
_version_check_event = threading.Event()
_version_check_message: Optional[str] = None


def _get_installed_version() -> Optional[str]:
    try:
        import importlib.metadata as _im  # py3.8+

        return _im.version("mcp-agent")
    except Exception:
        return None


def _parse_version(s: str):
    # Prefer packaging if available
    try:
        from packaging.version import parse as _vparse  # type: ignore

        return _vparse(s)
    except Exception:
        # Fallback: simple tuple of ints (non-PEP440 safe)
        return _simple_version_tuple(s)


def _simple_version_tuple(s: str):
    parts = s.split(".")
    out = []
    for p in parts:
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            out.append(int(num))
        else:
            break
    return tuple(out)


def _is_outdated(current: str, latest: str) -> bool:
    try:
        return _parse_version(latest) > _parse_version(current)
    except Exception:
        # Best-effort: if comparison fails, only warn when strings differ
        return latest != current


def _fetch_latest_version(timeout_seconds: float = 5.0) -> Optional[str]:
    try:
        import httpx

        url = "https://pypi.org/pypi/mcp-agent/json"
        timeout = httpx.Timeout(timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                version = (data or {}).get("info", {}).get("version")
                if isinstance(version, str) and version:
                    return version
    except Exception:
        pass
    return None


def _run_version_check() -> None:
    """Worker that performs the HTTP lookup and captures the message if needed."""
    global _version_check_message
    try:
        current = _get_installed_version()
        if not current:
            return

        latest = _fetch_latest_version(timeout_seconds=5.0)
        if not latest:
            return

        if _is_outdated(current, latest):
            _version_check_message = (
                "A new version of mcp-agent is available: "
                f"{current} -> {latest}. Update with: 'uv tool upgrade mcp-agent'"
            )
    finally:
        _version_check_event.set()


def _spawn_version_check_thread() -> None:
    thread = threading.Thread(
        target=_run_version_check,
        name="mcp-agent-version-check",
        daemon=True,
    )
    thread.start()


def _flush_version_check_message(timeout: float = 0.5) -> None:
    """Wait briefly for the background check and print any queued message."""
    if not _version_check_started:
        return

    _version_check_event.wait(timeout)
    message = _version_check_message
    if message:
        print_info(message, console_output=True)


def maybe_warn_newer_version() -> None:
    """Best-effort version check kicked off exactly once per process."""
    if os.environ.get("MCP_AGENT_DISABLE_VERSION_CHECK", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return

    if os.environ.get("MCP_AGENT_VERSION_CHECKED"):
        return

    with _version_check_lock:
        global _version_check_started, _version_check_message
        if _version_check_started:
            return
        _version_check_started = True
        _version_check_message = None
        _version_check_event.clear()

        try:
            _spawn_version_check_thread()
        except Exception:
            # Never allow version check issues to affect CLI usage
            _version_check_started = False
            return

        os.environ["MCP_AGENT_VERSION_CHECKED"] = "1"
        atexit.register(_flush_version_check_message)
