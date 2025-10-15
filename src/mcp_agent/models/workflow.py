"""Runtime workflow composition models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStep(BaseModel):
    id: str
    kind: str
    agent: Optional[str] = Field(default=None, description="Agent or tool identifier")
    config: Dict[str, Any] = Field(default_factory=dict)
    children: list["WorkflowStep"] = Field(default_factory=list)


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str | None = None
    root: WorkflowStep
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _normalize_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        raise TypeError("datetime values must be datetime or ISO formatted string")


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    updated_at: datetime
    step_count: int


class WorkflowPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowStepPatch(BaseModel):
    kind: Optional[str] = None
    agent: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


WorkflowStep.model_rebuild()

__all__ = [
    "WorkflowDefinition",
    "WorkflowPatch",
    "WorkflowStep",
    "WorkflowStepPatch",
    "WorkflowSummary",
]
