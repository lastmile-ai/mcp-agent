from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from mcp.types import CallToolRequest


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
    risk: RiskLevel
    reason: str
    rule_id: str


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    tool_call_id: str | None
    tool_name: str
    arguments_digest: str
    risk: str
    action: str
    outcome: str
    reason: str
    rule_id: str


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


ApprovalCallback = Callable[[NormalizedOperation, PolicyDecision], Awaitable[bool]]


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


class DefaultPolicy:
    """Small fail-closed policy for demonstrating the approval hook."""

    _READ_ONLY_COMMANDS = ("cat ", "git diff", "git status", "ls", "pwd")
    _SENSITIVE = re.compile(
        r"(?:^|[/\\\s\"'])(?:\.env(?:[./\\\s\"']|$)|\.ssh(?:[/\\\s\"']|$)|\.aws(?:[/\\\s\"']|$)|id_rsa|credentials)",
        re.IGNORECASE,
    )
    _EXFILTRATION = re.compile(
        r"\b(?:nc|netcat|scp)\b|\b(?:curl|wget)\b.*(?:--data|-d\s|--upload-file|@)",
        re.IGNORECASE,
    )

    def evaluate(self, operation: NormalizedOperation) -> PolicyDecision:
        tool_name = operation.tool_name.lower()
        arguments = json.dumps(operation.arguments, sort_keys=True, default=str)
        text = f"{tool_name} {arguments}".lower()

        if "--force" in text and "push" in text:
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.CRITICAL,
                "Force-push is prohibited by policy.",
                "critical.force_push",
            )
        if self._SENSITIVE.search(text):
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.CRITICAL,
                "Sensitive paths are prohibited by policy.",
                "critical.sensitive_path",
            )
        if self._EXFILTRATION.search(text):
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.CRITICAL,
                "The command resembles data exfiltration.",
                "critical.exfiltration",
            )
        if "sampling/createmessage" in text or "sampling_create_message" in text:
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.HIGH,
                "Sampling requires a separate, explicit approval path.",
                "high.sampling",
            )
        if any(token in text for token in ("delete", "remove_file", "rm -rf")):
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.HIGH,
                "Delete operations are blocked by default.",
                "high.delete",
            )
        if "push" in text:
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.HIGH,
                "Repository pushes are blocked by default.",
                "high.push",
            )
        if any(
            token in text
            for token in ("npm install", "pnpm add", "pip install", "uv add")
        ):
            return PolicyDecision(
                PolicyAction.REQUIRE_APPROVAL,
                RiskLevel.MEDIUM,
                "Package installation requires approval.",
                "medium.package_install",
            )
        if any(token in tool_name for token in ("write", "edit", "create_file")):
            return PolicyDecision(
                PolicyAction.REQUIRE_APPROVAL,
                RiskLevel.MEDIUM,
                "Workspace writes require approval.",
                "medium.write",
            )
        if any(token in tool_name for token in ("shell", "terminal", "run_command")):
            command = str(operation.arguments.get("command", "")).strip().lower()
            if command.startswith(self._READ_ONLY_COMMANDS):
                return PolicyDecision(
                    PolicyAction.ALLOW,
                    RiskLevel.LOW,
                    "Allowlisted read-only command.",
                    "low.read_only_command",
                )
            return PolicyDecision(
                PolicyAction.BLOCK,
                RiskLevel.HIGH,
                "Unknown shell commands are blocked by default.",
                "high.unknown_shell",
            )
        if any(token in tool_name for token in ("read", "list", "search", "get")):
            return PolicyDecision(
                PolicyAction.ALLOW,
                RiskLevel.LOW,
                "Read-only tool is allowlisted.",
                "low.read_only_tool",
            )
        return PolicyDecision(
            PolicyAction.BLOCK,
            RiskLevel.HIGH,
            "Unknown tools are blocked by default.",
            "high.unknown_tool",
        )


class JsonlAuditSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def append(self, event: AuditEvent) -> None:
        await asyncio.to_thread(self._append, event)

    def _append(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")


class PolicyGateway:
    def __init__(
        self,
        policy: DefaultPolicy,
        approval_callback: ApprovalCallback,
        audit_sink: AuditSink,
    ) -> None:
        self.policy = policy
        self.approval_callback = approval_callback
        self.audit_sink = audit_sink

    async def authorize(
        self, request: CallToolRequest, tool_call_id: str | None = None
    ) -> bool:
        operation = normalize_operation(request)
        decision = self.policy.evaluate(operation)

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
                risk=decision.risk.value,
                action=decision.action.value,
                outcome=outcome,
                reason=decision.reason,
                rule_id=decision.rule_id,
            )
        )
        return approved


async def console_approval(
    operation: NormalizedOperation, decision: PolicyDecision
) -> bool:
    prompt = (
        f"Approve {operation.tool_name} ({decision.risk.value}): "
        f"{json.dumps(operation.arguments, default=str)}? [y/N] "
    )
    response = await asyncio.to_thread(input, prompt)
    return response.strip().lower() in {"y", "yes"}
