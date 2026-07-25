import json

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams

from examples.basic.mcp_tool_approval.policy_gateway import (
    AuditEvent,
    DefaultPolicy,
    JsonlAuditSink,
    PolicyGateway,
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


@pytest.mark.asyncio
async def test_read_only_tool_is_allowed_without_approval() -> None:
    approvals = 0

    async def approve(*_args) -> bool:
        nonlocal approvals
        approvals += 1
        return True

    audit = MemoryAuditSink()
    gateway = PolicyGateway(DefaultPolicy(), approve, audit)

    allowed = await gateway.authorize(
        request("filesystem_read_file", {"path": "README.md"}), "call-1"
    )

    assert allowed is True
    assert approvals == 0
    assert audit.events[0].outcome == "allowed"
    assert audit.events[0].risk == "low"


@pytest.mark.asyncio
async def test_workspace_write_requires_approval() -> None:
    async def approve(*_args) -> bool:
        return True

    audit = MemoryAuditSink()
    gateway = PolicyGateway(DefaultPolicy(), approve, audit)

    allowed = await gateway.authorize(
        request(
            "filesystem_write_file",
            {"path": "src/example.py", "content": "print('ok')"},
        )
    )

    assert allowed is True
    assert audit.events[0].action == "require_approval"
    assert audit.events[0].outcome == "approved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_rule"),
    [
        ("filesystem_delete_file", {"path": "src/example.py"}, "high.delete"),
        (
            "terminal_run_command",
            {"command": "git push --force origin main"},
            "critical.force_push",
        ),
    ],
)
async def test_blocked_operations_never_request_approval(
    tool_name: str, arguments: dict, expected_rule: str
) -> None:
    approvals = 0

    async def approve(*_args) -> bool:
        nonlocal approvals
        approvals += 1
        return True

    audit = MemoryAuditSink()
    gateway = PolicyGateway(DefaultPolicy(), approve, audit)

    allowed = await gateway.authorize(request(tool_name, arguments))

    assert allowed is False
    assert approvals == 0
    assert audit.events[0].rule_id == expected_rule
    assert audit.events[0].outcome == "blocked"


@pytest.mark.asyncio
async def test_jsonl_audit_persists_digest_without_raw_arguments(tmp_path) -> None:
    async def approve(*_args) -> bool:
        return False

    audit_path = tmp_path / "policy-audit.jsonl"
    gateway = PolicyGateway(DefaultPolicy(), approve, JsonlAuditSink(audit_path))

    await gateway.authorize(
        request(
            "filesystem_read_file",
            {"path": ".env", "token": "sk-sensitive-example"},
        )
    )

    raw = audit_path.read_text(encoding="utf-8")
    event = json.loads(raw)
    assert event["rule_id"] == "critical.sensitive_path"
    assert len(event["arguments_digest"]) == 64
    assert ".env" not in raw
    assert "sk-sensitive-example" not in raw
