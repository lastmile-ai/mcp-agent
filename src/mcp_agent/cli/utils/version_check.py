"""Best-effort PyPI version check for mcp-agent.

- Contacts PyPI JSON API for latest version
- Compares with installed version
- Prints an info hint if an update is available
- Times out after 5 seconds and never raises
"""

from __future__ import annotations

import os
from typing import Optional

from mcp_agent.cli.utils.ux import print_info


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


def maybe_warn_newer_version() -> None:
    """Best-effort, once-per-process, 5s-timeout version check.

    Honors env var MCP_AGENT_DISABLE_VERSION_CHECK=true/1/yes to skip.
    """
    if os.environ.get("MCP_AGENT_DISABLE_VERSION_CHECK", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return

    # Ensure we run at most once per process
    if os.environ.get("MCP_AGENT_VERSION_CHECKED"):
        return
    os.environ["MCP_AGENT_VERSION_CHECKED"] = "1"

    current = _get_installed_version()
    if not current:
        return

    latest = _fetch_latest_version(timeout_seconds=5.0)
    if not latest:
        return

    if _is_outdated(current, latest):
        print_info(
            f"A new version of mcp-agent is available: {current} -> {latest}. Update with: 'uv tool update mcp-agent'",
            console_output=True,
        )
