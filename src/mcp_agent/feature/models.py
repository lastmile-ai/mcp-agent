"""Data models describing the feature intake lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class FeatureState(str, Enum):
    DRAFTING = "feature_drafting"
    ESTIMATED = "feature_estimated"
    AWAITING_CONFIRMATION = "awaiting_budget_confirmation"
    CONFIRMED = "budget_confirmed"
    REJECTED = "budget_rejected"
    CANCELLED = "feature_cancelled"


@dataclass
class FeatureMessage:
    role: MessageRole
    content: str
    created_at: datetime = field(default_factory=_utc_now)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.strftime(ISO_FORMAT),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FeatureMessage":
        role = MessageRole(payload.get("role", MessageRole.USER))
        created_raw = payload.get("created_at")
        if created_raw:
            created_at = datetime.strptime(created_raw, ISO_FORMAT).replace(tzinfo=timezone.utc)
        else:
            created_at = _utc_now()
        return cls(role=role, content=str(payload.get("content", "")), created_at=created_at)


@dataclass
class FeatureSpec:
    summary: str
    details: str
    targets: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        bullets = ["# Feature Summary", self.summary, "", "## Details", self.details]
        if self.targets:
            bullets.extend(["", "## Targets"])
            bullets.extend(f"- {item}" for item in self.targets)
        if self.risks:
            bullets.extend(["", "## Risks"])
            bullets.extend(f"- {item}" for item in self.risks)
        return "\n".join(bullets)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "details": self.details,
            "targets": list(self.targets),
            "risks": list(self.risks),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FeatureSpec":
        return cls(
            summary=str(payload.get("summary", "")).strip(),
            details=str(payload.get("details", "")).strip(),
            targets=[str(item) for item in payload.get("targets", [])],
            risks=[str(item) for item in payload.get("risks", [])],
        )


@dataclass
class BudgetEstimate:
    seconds: int
    rationale: str
    iterations: int
    caps: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seconds": int(self.seconds),
            "rationale": self.rationale,
            "iterations": int(self.iterations),
            "caps": dict(self.caps),
        }


@dataclass
class BudgetDecision:
    seconds: int
    approved: bool
    rationale: str | None = None
    decided_at: datetime = field(default_factory=_utc_now)

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "seconds": int(self.seconds),
            "approved": bool(self.approved),
            "decided_at": self.decided_at.strftime(ISO_FORMAT),
        }
        if self.rationale:
            payload["rationale"] = self.rationale
        return payload


@dataclass
class FeatureDraft:
    feature_id: str
    project_id: str
    trace_id: str
    messages: List[FeatureMessage] = field(default_factory=list)
    state: FeatureState = FeatureState.DRAFTING
    spec: FeatureSpec | None = None
    estimate: BudgetEstimate | None = None
    decision: BudgetDecision | None = None
    cancelled_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def append(self, message: FeatureMessage) -> None:
        self.messages.append(message)
        self.updated_at = _utc_now()

    def set_state(self, new_state: FeatureState) -> None:
        self.state = new_state
        self.updated_at = _utc_now()

    def set_spec(self, spec: FeatureSpec) -> None:
        self.spec = spec
        self.updated_at = _utc_now()

    def set_estimate(self, estimate: BudgetEstimate) -> None:
        self.estimate = estimate
        self.updated_at = _utc_now()

    def set_decision(self, decision: BudgetDecision) -> None:
        self.decision = decision
        self.updated_at = _utc_now()

    def cancel(self) -> None:
        self.state = FeatureState.CANCELLED
        self.cancelled_at = _utc_now()
        self.updated_at = self.cancelled_at

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "feature_id": self.feature_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "state": self.state.value,
            "messages": [msg.as_dict() for msg in self.messages],
            "created_at": self.created_at.strftime(ISO_FORMAT),
            "updated_at": self.updated_at.strftime(ISO_FORMAT),
        }
        if self.spec:
            payload["spec"] = self.spec.as_dict()
        if self.estimate:
            payload["estimate"] = self.estimate.as_dict()
        if self.decision:
            payload["decision"] = self.decision.as_dict()
        if self.cancelled_at:
            payload["cancelled_at"] = self.cancelled_at.strftime(ISO_FORMAT)
        return payload

    def transcript(self) -> List[Dict[str, Any]]:
        return [msg.as_dict() for msg in self.messages]


__all__ = [
    "BudgetDecision",
    "BudgetEstimate",
    "FeatureDraft",
    "FeatureMessage",
    "FeatureSpec",
    "FeatureState",
    "MessageRole",
]
