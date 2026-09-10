"""HOL Guard pre-tool approval hook for mcp-agent examples.

The example keeps HOL Guard outside mcp-agent's dependencies. Configure the
command with ``HOL_GUARD_COMMAND`` (default: ``hol-guard``). The command receives
one JSON object on stdin and should print JSON containing either
``{"decision": "allow"}`` or ``{"allow": true}`` to let the tool execute.
Anything else fails closed.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolRequest

GuardRunner = Callable[[dict[str, Any]], dict[str, Any]]

_ALLOWED_DECISIONS = {"allow", "allowed", "safe", "pass"}


def _default_hol_guard_runner(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the configured HOL Guard command and parse its JSON decision."""
    command = os.environ.get("HOL_GUARD_COMMAND", "hol-guard")
    completed = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=float(os.environ.get("HOL_GUARD_TIMEOUT_SECONDS", "10")),
        check=False,
    )
    if completed.returncode != 0:
        return {
            "decision": "deny",
            "reason": completed.stderr.strip() or f"exit {completed.returncode}",
        }

    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"decision": "deny", "reason": f"invalid HOL Guard JSON: {exc}"}

    if not isinstance(parsed, dict):
        return {"decision": "deny", "reason": "HOL Guard returned non-object JSON"}
    return parsed


def _is_allowed(decision: dict[str, Any]) -> bool:
    """Return true only for explicit safe/allow decisions."""
    if decision.get("allow") is True:
        return True
    status = (
        decision.get("decision") or decision.get("status") or decision.get("result")
    )
    return isinstance(status, str) and status.lower() in _ALLOWED_DECISIONS


class HolGuardToolApprovalMixin:
    """Mixin that asks HOL Guard before each MCP tool call."""

    guard_runner: GuardRunner = _default_hol_guard_runner

    async def pre_tool_call(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, tool_call_id: str | None, request: CallToolRequest
    ) -> CallToolRequest | bool:
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": request.params.name,
            "arguments": request.params.arguments or {},
        }
        runner = getattr(self, "guard_runner", _default_hol_guard_runner)
        try:
            decision = await asyncio.to_thread(runner, payload)
        except Exception:  # noqa: BLE001 - fail closed for any guard failure.
            return False

        if _is_allowed(decision):
            return request
        return False


try:
    from mcp_agent.workflows.llm.augmented_llm_openai import (
        OpenAIAugmentedLLM,  # pyright: ignore[reportMissingImports]
    )
except ModuleNotFoundError as exc:
    _OPENAI_IMPORT_ERROR = exc

    class HolGuardedOpenAIAugmentedLLM:  # type: ignore[no-redef]
        """Placeholder used when the optional OpenAI extra is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ModuleNotFoundError(
                "Install the OpenAI extra before running this example: "
                "uv pip install -r examples/basic/hol_guard_tool_approval/requirements.txt"
            ) from _OPENAI_IMPORT_ERROR

else:

    class HolGuardedOpenAIAugmentedLLM(  # type: ignore[no-redef]
        HolGuardToolApprovalMixin, OpenAIAugmentedLLM
    ):
        """OpenAI LLM example that asks HOL Guard before each MCP tool call."""
