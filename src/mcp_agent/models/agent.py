"""Agent-centric API schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mcp_agent.agents.agent_spec import AgentSpec


class AgentSpecPayload(BaseModel):
    """Payload used to create a new :class:`AgentSpec`."""

    name: str = Field(..., description="Unique identifier for the agent.")
    instruction: Optional[str] = Field(
        default=None, description="Default high level instruction for the agent."
    )
    server_names: list[str] = Field(
        default_factory=list,
        description="MCP server names the agent should connect to by default.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Free-form metadata stored alongside the spec."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional tag list used for UI filtering and grouping.",
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional keyword arguments forwarded to the AgentSpec constructor.",
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _merge_extra(self) -> "AgentSpecPayload":
        for key, value in list(self.model_extra.items()):
            if key in self.model_fields:
                continue
            self.extra[key] = value
            del self.model_extra[key]
        return self

    def build_spec(self) -> AgentSpec:
        """Return an :class:`AgentSpec` instance for this payload."""

        payload: Dict[str, Any] = {
            "name": self.name,
            "instruction": self.instruction,
            "server_names": list(self.server_names),
        }
        payload.update(self.extra)
        return AgentSpec(**payload)


class AgentSpecPatch(BaseModel):
    """Patch payload for updating an :class:`AgentSpec`."""

    name: Optional[str] = None
    instruction: Optional[str] = None
    server_names: Optional[list[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[list[str]] = None
    extra: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _merge_extra(self) -> "AgentSpecPatch":
        if self.extra is None:
            self.extra = {}
        for key, value in list(self.model_extra.items()):
            if key in self.model_fields:
                continue
            self.extra[key] = value
            del self.model_extra[key]
        return self


class AgentSpecEnvelope(BaseModel):
    """Envelope returned for a single agent specification."""

    id: str
    spec: AgentSpec
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp in UTC.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last modification timestamp in UTC.",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def with_updates(self, **updates: Any) -> "AgentSpecEnvelope":
        data = self.model_dump()
        data.update(updates)
        return AgentSpecEnvelope(**data)


class AgentSpecListResponse(BaseModel):
    """List response for agent specifications."""

    items: list[AgentSpecEnvelope]
    total: int


__all__ = [
    "AgentSpecEnvelope",
    "AgentSpecListResponse",
    "AgentSpecPatch",
    "AgentSpecPayload",
]
