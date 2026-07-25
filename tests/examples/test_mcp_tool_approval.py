import json
import os
from pathlib import Path

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams

from examples.basic.mcp_tool_approval.policy_gateway import (
    ApprovalGate,
    ApprovalHook,
    AuditEvent,
    JsonlAuditSink,
    filesystem_policy,
)


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)


def request(name: str, arguments: dict) -> CallToolRequest:
    return CallToolRequest(
        agent_name="test-agent",
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )


def hook_with_gate(gate: ApprovalGate) -> ApprovalHook:
    hook = ApprovalHook()
    hook.approval_gate = gate
    return hook


@pytest.mark.asyncio
async def test_pre_tool_call_allows_exact_read_without_approval() -> None:
    approvals = 0

    async def approve(*_args) -> bool:
        nonlocal approvals
        approvals += 1
        return True

    audit = MemoryAuditSink()
    hook = hook_with_gate(ApprovalGate(filesystem_policy, approve, audit))
    tool_request = request("filesystem_read_file", {"path": "README.md"})

    result = await hook.pre_tool_call("call-1", tool_request)

    assert result is tool_request
    assert approvals == 0
    assert audit.events[0].outcome == "allowed"
    assert audit.events[0].tool_call_id == "call-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approval_result", "expected_result", "expected_outcome"),
    [(True, "request", "approved"), (False, "blocked", "approval_declined")],
)
async def test_pre_tool_call_uses_approval_for_exact_write(
    approval_result: bool, expected_result: str, expected_outcome: str
) -> None:
    async def approve(*_args) -> bool:
        return approval_result

    audit = MemoryAuditSink()
    hook = hook_with_gate(ApprovalGate(filesystem_policy, approve, audit))
    tool_request = request(
        "filesystem_write_file",
        {"path": "src/example.py", "content": "print('ok')"},
    )

    result = await hook.pre_tool_call(None, tool_request)

    if expected_result == "request":
        assert result is tool_request
    else:
        assert result is False
    assert audit.events[0].outcome == expected_outcome


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("filesystem_delete_file", {"path": "src/example.py"}),
        ("filesystem_read_file_backup", {"path": "README.md"}),
        ("terminal_run_command", {"command": "git status && git push"}),
    ],
)
async def test_pre_tool_call_blocks_unknown_tools_without_approval(
    tool_name: str, arguments: dict
) -> None:
    approvals = 0

    async def approve(*_args) -> bool:
        nonlocal approvals
        approvals += 1
        return True

    audit = MemoryAuditSink()
    hook = hook_with_gate(ApprovalGate(filesystem_policy, approve, audit))

    result = await hook.pre_tool_call(None, request(tool_name, arguments))

    assert result is False
    assert approvals == 0
    assert audit.events[0].outcome == "blocked"


@pytest.mark.asyncio
async def test_sensitive_path_is_blocked_and_audit_omits_arguments() -> None:
    async def approve(*_args) -> bool:
        return True

    audit_path = Path("logs") / f"policy-audit-test-{os.getpid()}.jsonl"
    gate = ApprovalGate(
        filesystem_policy,
        approve,
        JsonlAuditSink(audit_path),
    )

    try:
        allowed = await gate.authorize(
            request(
                "filesystem_read_multiple_files",
                {
                    "paths": ["README.md", ".env.local"],
                    "token": "sk-sensitive-example",
                },
            )
        )

        raw = audit_path.read_text(encoding="utf-8")
        event = json.loads(raw)
        assert allowed is False
        assert event["outcome"] == "blocked"
        assert len(event["arguments_digest"]) == 64
        assert ".env.local" not in raw
        assert "sk-sensitive-example" not in raw
    finally:
        audit_path.unlink(missing_ok=True)
