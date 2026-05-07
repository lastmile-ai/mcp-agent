"""Audit records for agent tool-call governance decisions."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ToolCallDecision(str, Enum):
    """Policy decision for a tool call before it executes."""

    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"
    NEEDS_REVIEW = "needs_review"


class ToolCallAuditRecord(BaseModel):
    """Redacted governance record for an agent tool call.

    The record intentionally stores hashes of arguments instead of raw argument
    values so it can be written to audit logs without leaking private payloads.
    """

    schema_version: str = "mcp-agent-tool-call-audit-v1"
    event_id: str
    tool_name: str
    decision: ToolCallDecision
    args_hash: str
    policy_id: str
    policy_version: str
    evaluated_at: str
    agent_name: str | None = None
    call_id: str | None = None
    modified_args_hash: str | None = None
    reason: str | None = None
    redacted_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("args_hash", "modified_args_hash")
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("hashes must use the sha256:<hex-digest> format")
        return value

    @model_validator(mode="after")
    def require_modified_hash_for_modify(self) -> "ToolCallAuditRecord":
        if (
            self.decision == ToolCallDecision.MODIFY
            and self.modified_args_hash is None
        ):
            raise ValueError("modified_args_hash is required for modify decisions")
        return self


def hash_tool_arguments(arguments: dict[str, Any] | None) -> str:
    """Return a stable SHA-256 hash for tool-call arguments."""

    canonical = json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def validate_tool_call_audit_record(record: ToolCallAuditRecord) -> None:
    """Validate decision-specific safety properties for audit records."""

    if record.decision in {ToolCallDecision.DENY, ToolCallDecision.NEEDS_REVIEW}:
        if not record.reason:
            raise ValueError("reason is required for deny and needs_review decisions")

    if record.decision == ToolCallDecision.MODIFY:
        if record.modified_args_hash == record.args_hash:
            raise ValueError("modify decisions must change the argument hash")

    if _contains_raw_arguments(record.metadata):
        raise ValueError("metadata must not contain raw tool arguments")


def _contains_raw_arguments(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in {"args", "arguments", "raw_args", "raw_arguments"}:
                return True
            if _contains_raw_arguments(nested_value):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_arguments(item) for item in value)
    return False
