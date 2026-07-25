from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from mcp.types import CallToolRequest


class PolicyAction(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


@dataclass(frozen=True)
class NormalizedOperation:
    tool_name: str
    arguments_digest: str
    arguments: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reason: str


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    tool_call_id: str | None
    tool_name: str
    arguments_digest: str
    action: str
    outcome: str
    reason: str


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


DecisionFunction = Callable[[NormalizedOperation], PolicyDecision]
ApprovalCallback = Callable[[NormalizedOperation, PolicyDecision], Awaitable[bool]]

READ_ONLY_FILESYSTEM_TOOLS = frozenset(
    {
        "filesystem_directory_tree",
        "filesystem_get_file_info",
        "filesystem_list_allowed_directories",
        "filesystem_list_directory",
        "filesystem_list_directory_with_sizes",
        "filesystem_read_file",
        "filesystem_read_media_file",
        "filesystem_read_multiple_files",
        "filesystem_read_text_file",
        "filesystem_search_files",
    }
)
WRITING_FILESYSTEM_TOOLS = frozenset(
    {
        "filesystem_create_directory",
        "filesystem_edit_file",
        "filesystem_move_file",
        "filesystem_write_file",
    }
)
PATH_ARGUMENT_NAMES = frozenset({"destination", "path", "paths", "source"})
SENSITIVE_PATH_PARTS = frozenset(
    {".aws", ".ssh", "credentials", "id_ed25519", "id_rsa"}
)


def normalize_operation(request: CallToolRequest) -> NormalizedOperation:
    arguments = dict(request.params.arguments or {})
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return NormalizedOperation(
        tool_name=request.params.name,
        arguments_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        arguments=arguments,
    )


def filesystem_policy(operation: NormalizedOperation) -> PolicyDecision:
    if _references_sensitive_path(operation.arguments):
        return PolicyDecision(
            PolicyAction.BLOCK,
            "Sensitive paths are blocked by this example.",
        )
    if operation.tool_name in READ_ONLY_FILESYSTEM_TOOLS:
        return PolicyDecision(
            PolicyAction.ALLOW,
            "Exact allowlisted read-only filesystem tool.",
        )
    if operation.tool_name in WRITING_FILESYSTEM_TOOLS:
        return PolicyDecision(
            PolicyAction.REQUIRE_APPROVAL,
            "Filesystem changes require approval.",
        )
    return PolicyDecision(
        PolicyAction.BLOCK,
        "Tool is not in the example's exact allowlist.",
    )


def _references_sensitive_path(arguments: Mapping[str, Any]) -> bool:
    for name in PATH_ARGUMENT_NAMES:
        value = arguments.get(name)
        values = value if isinstance(value, list) else [value]
        for candidate in values:
            if not isinstance(candidate, str):
                continue
            parts = {
                part.lower() for part in candidate.replace("\\", "/").split("/") if part
            }
            if any(
                part in SENSITIVE_PATH_PARTS
                or part == ".env"
                or part.startswith(".env.")
                for part in parts
            ):
                return True
    return False


class JsonlAuditSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def append(self, event: AuditEvent) -> None:
        await asyncio.to_thread(self._append, event)

    def _append(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            os.chmod(self.path, 0o600)
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")


class ApprovalGate:
    def __init__(
        self,
        decide: DecisionFunction,
        approval_callback: ApprovalCallback,
        audit_sink: AuditSink,
    ) -> None:
        self.decide = decide
        self.approval_callback = approval_callback
        self.audit_sink = audit_sink

    async def authorize(
        self, request: CallToolRequest, tool_call_id: str | None = None
    ) -> bool:
        operation = normalize_operation(request)
        decision = self.decide(operation)

        approved = decision.action is PolicyAction.ALLOW
        outcome = "allowed" if approved else "blocked"
        if decision.action is PolicyAction.REQUIRE_APPROVAL:
            approved = await self.approval_callback(operation, decision)
            outcome = "approved" if approved else "approval_declined"

        await self.audit_sink.append(
            AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                tool_call_id=tool_call_id,
                tool_name=operation.tool_name,
                arguments_digest=operation.arguments_digest,
                action=decision.action.value,
                outcome=outcome,
                reason=decision.reason,
            )
        )
        return approved


class ApprovalHook:
    approval_gate: ApprovalGate

    async def pre_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest
    ) -> CallToolRequest | bool:
        if await self.approval_gate.authorize(request, tool_call_id):
            return request
        return False


async def console_approval(
    operation: NormalizedOperation, decision: PolicyDecision
) -> bool:
    prompt = (
        f"Approve {operation.tool_name}: "
        f"{json.dumps(operation.arguments, default=str)}? [y/N] "
    )
    response = await asyncio.to_thread(input, prompt)
    return response.strip().lower() in {"y", "yes"}
