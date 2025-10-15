"""Data structures describing orchestrator state for the admin API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrchestratorQueueItem(BaseModel):
    id: str
    agent: str
    created_at: datetime = Field(default_factory=_utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", mode="before")
    @classmethod
    def _normalize_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        raise TypeError("created_at must be datetime or ISO formatted string")


class OrchestratorPlanNode(BaseModel):
    id: str
    name: str
    status: str = Field(default="pending")
    agent: Optional[str] = None
    children: list["OrchestratorPlanNode"] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestratorPlan(BaseModel):
    root: Optional[OrchestratorPlanNode] = None
    version: int = Field(default=0, ge=0)


class OrchestratorState(BaseModel):
    id: str
    status: str = Field(default="idle")
    active_agents: list[str] = Field(default_factory=list)
    budget_seconds_remaining: Optional[float] = Field(default=None, ge=0.0)
    policy: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=_utc_now)

    @field_validator("last_updated", mode="before")
    @classmethod
    def _normalize_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        raise TypeError("last_updated must be datetime or ISO formatted string")


class OrchestratorSnapshot(BaseModel):
    state: OrchestratorState
    queue: list[OrchestratorQueueItem] = Field(default_factory=list)
    plan: OrchestratorPlan = Field(default_factory=OrchestratorPlan)


class OrchestratorStatePatch(BaseModel):
    status: Optional[str] = None
    active_agents: Optional[List[str]] = None
    budget_seconds_remaining: Optional[float] = Field(default=None, ge=0.0)
    policy: Optional[Dict[str, Any]] = None
    memory: Optional[Dict[str, Any]] = None


class OrchestratorEvent(BaseModel):
    """Event pushed on the orchestrator SSE stream."""

    id: int
    timestamp: datetime = Field(default_factory=_utc_now)
    type: str = Field(default="update")
    payload: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "OrchestratorEvent",
    "OrchestratorPlan",
    "OrchestratorPlanNode",
    "OrchestratorQueueItem",
    "OrchestratorSnapshot",
    "OrchestratorState",
    "OrchestratorStatePatch",
]

OrchestratorPlanNode.model_rebuild()
