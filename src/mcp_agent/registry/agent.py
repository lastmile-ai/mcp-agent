"""Runtime registry for managing :class:`AgentSpec` definitions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Mapping, MutableMapping

import yaml

from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.logging.logger import get_logger
from mcp_agent.models.agent import AgentSpecEnvelope, AgentSpecPatch, AgentSpecPayload

logger = get_logger(__name__)


@dataclass
class _AgentEntry:
    spec: AgentSpec
    metadata: MutableMapping[str, object] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_path: Path | None = None


class AgentRegistryError(RuntimeError):
    """Base error for agent registry operations."""


class AgentNotFoundError(AgentRegistryError):
    """Raised when attempting to mutate a missing agent."""


class AgentAlreadyExistsError(AgentRegistryError):
    """Raised when creating a duplicate agent spec."""


class AgentRegistry:
    """Tracks agent specifications loaded at runtime."""

    def __init__(self) -> None:
        self._entries: Dict[str, _AgentEntry] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    async def list(self) -> list[AgentSpecEnvelope]:
        async with self._lock:
            return [self._to_envelope(agent_id, entry) for agent_id, entry in self._entries.items()]

    async def get(self, agent_id: str) -> AgentSpecEnvelope:
        async with self._lock:
            entry = self._entries.get(agent_id)
            if entry is None:
                raise AgentNotFoundError(agent_id)
            return self._to_envelope(agent_id, entry)

    async def create(self, payload: AgentSpecPayload) -> AgentSpecEnvelope:
        spec = payload.build_spec()
        metadata = dict(payload.metadata)
        tags = sorted(set(payload.tags))
        async with self._lock:
            if spec.name in self._entries:
                raise AgentAlreadyExistsError(spec.name)
            entry = _AgentEntry(spec=spec, metadata=metadata, tags=tags)
            self._entries[spec.name] = entry
            logger.info("agent.registry.create", agent=spec.name)
            return self._to_envelope(spec.name, entry)

    async def update(self, agent_id: str, patch: AgentSpecPatch) -> AgentSpecEnvelope:
        async with self._lock:
            entry = self._entries.get(agent_id)
            if entry is None:
                raise AgentNotFoundError(agent_id)

            update_payload: Dict[str, object] = {}
            if patch.name:
                if patch.name != agent_id and patch.name in self._entries:
                    raise AgentAlreadyExistsError(patch.name)
                update_payload["name"] = patch.name
            if patch.instruction is not None:
                update_payload["instruction"] = patch.instruction
            if patch.server_names is not None:
                update_payload["server_names"] = patch.server_names
            if patch.extra:
                update_payload.update(patch.extra)

            if update_payload:
                entry.spec = entry.spec.model_copy(update=update_payload)
            if patch.metadata is not None:
                entry.metadata = dict(patch.metadata)
            if patch.tags is not None:
                entry.tags = sorted(set(patch.tags))

            new_id = entry.spec.name
            if new_id != agent_id:
                self._entries[new_id] = entry
                del self._entries[agent_id]
                agent_id = new_id

            entry.updated_at = datetime.now(timezone.utc)
            logger.info("agent.registry.update", agent=agent_id)
            return self._to_envelope(agent_id, entry)

    async def delete(self, agent_id: str) -> None:
        async with self._lock:
            if agent_id not in self._entries:
                raise AgentNotFoundError(agent_id)
            del self._entries[agent_id]
            logger.info("agent.registry.delete", agent=agent_id)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()

    async def export_yaml(self) -> str:
        """Return all registered agents as YAML."""

        async with self._lock:
            data = [entry.spec.model_dump(mode="json") for entry in self._entries.values()]
        return yaml.safe_dump({"agents": data}, sort_keys=False)

    async def import_yaml(self, text: str, *, replace: bool = False) -> list[AgentSpecEnvelope]:
        """Load AgentSpec entries from YAML text."""

        loaded = yaml.safe_load(text) or {}
        agents: Iterable[Mapping[str, object]] = []
        if isinstance(loaded, Mapping):
            if "agents" in loaded and isinstance(loaded["agents"], Iterable):
                agents = loaded["agents"]
            else:
                agents = [loaded]
        elif isinstance(loaded, list):
            agents = loaded
        else:
            raise ValueError("agents YAML must be a mapping or list")

        new_entries: Dict[str, _AgentEntry] = {}
        for item in agents:
            if not isinstance(item, Mapping):
                continue
            payload = AgentSpecPayload(**item)
            spec = payload.build_spec()
            new_entries[spec.name] = _AgentEntry(
                spec=spec,
                metadata=dict(payload.metadata),
                tags=sorted(set(payload.tags)),
            )

        async with self._lock:
            if replace:
                self._entries.clear()
            for agent_id, entry in new_entries.items():
                self._entries[agent_id] = entry
        return [self._to_envelope(agent_id, entry) for agent_id, entry in new_entries.items()]

    # ------------------------------------------------------------------
    def _to_envelope(self, agent_id: str, entry: _AgentEntry) -> AgentSpecEnvelope:
        return AgentSpecEnvelope(
            id=agent_id,
            spec=entry.spec,
            metadata=dict(entry.metadata),
            tags=list(entry.tags),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


agent_registry = AgentRegistry()

__all__ = [
    "AgentAlreadyExistsError",
    "AgentNotFoundError",
    "AgentRegistry",
    "AgentRegistryError",
    "agent_registry",
]
