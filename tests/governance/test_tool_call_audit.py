import pytest
from pydantic import ValidationError

from mcp_agent.governance.tool_call_audit import (
    ToolCallAuditRecord,
    ToolCallDecision,
    hash_tool_arguments,
    validate_tool_call_audit_record,
)


def test_hash_tool_arguments_is_stable_for_key_order() -> None:
    first = hash_tool_arguments({"path": "/tmp/report.txt", "limit": 10})
    second = hash_tool_arguments({"limit": 10, "path": "/tmp/report.txt"})

    assert first == second
    assert first.startswith("sha256:")


def test_allow_record_validates_without_raw_arguments() -> None:
    record = ToolCallAuditRecord(
        event_id="evt_001",
        tool_name="filesystem_write",
        decision=ToolCallDecision.ALLOW,
        args_hash=hash_tool_arguments({"path": "/tmp/report.txt"}),
        policy_id="default-tool-policy",
        policy_version="2026-05-07",
        evaluated_at="2026-05-07T00:00:00Z",
        redacted_fields=["arguments.path"],
        metadata={"risk": "low"},
    )

    validate_tool_call_audit_record(record)


def test_deny_record_requires_reason() -> None:
    record = ToolCallAuditRecord(
        event_id="evt_002",
        tool_name="filesystem_delete",
        decision=ToolCallDecision.DENY,
        args_hash=hash_tool_arguments({"path": "/tmp/report.txt"}),
        policy_id="default-tool-policy",
        policy_version="2026-05-07",
        evaluated_at="2026-05-07T00:00:00Z",
    )

    with pytest.raises(ValueError, match="reason is required"):
        validate_tool_call_audit_record(record)


def test_modify_record_requires_modified_args_hash() -> None:
    with pytest.raises(ValidationError, match="modified_args_hash"):
        ToolCallAuditRecord(
            event_id="evt_003",
            tool_name="web_search",
            decision=ToolCallDecision.MODIFY,
            args_hash=hash_tool_arguments({"limit": 1000}),
            policy_id="default-tool-policy",
            policy_version="2026-05-07",
            evaluated_at="2026-05-07T00:00:00Z",
        )


def test_rejects_raw_arguments_in_metadata() -> None:
    record = ToolCallAuditRecord(
        event_id="evt_004",
        tool_name="send_email",
        decision=ToolCallDecision.NEEDS_REVIEW,
        args_hash=hash_tool_arguments({"recipient": "user@example.com"}),
        policy_id="default-tool-policy",
        policy_version="2026-05-07",
        evaluated_at="2026-05-07T00:00:00Z",
        reason="external communication requires review",
        metadata={"arguments": {"recipient": "user@example.com"}},
    )

    with pytest.raises(ValueError, match="raw tool arguments"):
        validate_tool_call_audit_record(record)
