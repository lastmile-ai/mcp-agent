"""Pydantic models and helper types for the tools registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ToolItem(BaseModel):
    """Normalized representation of an MCP tool server."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    name: str
    version: str = Field(default="0.0.0")
    base_url: str
    alive: bool
    latency_ms: float = Field(default=0.0, ge=0.0)
    capabilities: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    last_checked_ts: datetime = Field(default_factory=lambda: _ensure_utc(datetime.now(timezone.utc)))
    failure_reason: Optional[str] = None
    consecutive_failures: int = Field(default=0, ge=0)

    @field_validator("capabilities", "tags", mode="after")
    @classmethod
    def _sort_list(cls, value: Iterable[str]) -> List[str]:
        return sorted({str(item) for item in value})

    @field_validator("last_checked_ts", mode="before")
    @classmethod
    def _normalize_dt(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("last_checked_ts must be datetime or ISO string")

    @field_validator("latency_ms", mode="after")
    @classmethod
    def _round_latency(cls, value: float) -> float:
        return round(float(value), 1)


class ToolsResponse(BaseModel):
    """Response envelope for the tools registry API."""

    model_config = ConfigDict(extra="ignore")

    registry_hash: str
    generated_at: datetime
    items: List[ToolItem] = Field(default_factory=list)

    @field_validator("generated_at", mode="before")
    @classmethod
    def _normalize_generated_at(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("generated_at must be datetime or ISO string")

    def with_items(self, items: Iterable[ToolItem]) -> "ToolsResponse":
        return ToolsResponse(
            registry_hash=self.registry_hash,
            generated_at=self.generated_at,
            items=list(items),
        )


@dataclass
class ToolSource:
    """Static definition of a tool server from configuration."""

    id: str
    name: str
    base_url: str
    headers: dict[str, str]
    tags: List[str]


@dataclass
class ToolProbeResult:
    """Result of probing a tool source."""

    id: str
    name: str
    version: str
    base_url: str
    alive: bool
    latency_ms: float
    capabilities: List[str]
    tags: List[str]
    timestamp: datetime
    failure_reason: Optional[str]

