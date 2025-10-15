"""Utility helpers for runtime tool registry management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, MutableMapping

from mcp_agent.registry.models import ToolItem
from mcp_agent.registry.store import store


@dataclass
class ToolAssignment:
    tool_id: str
    enabled: bool = True
    assigned_agents: set[str] = field(default_factory=set)


class ToolRuntimeRegistry:
    """Runtime overlay providing enable/disable and assignment state."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._overrides: Dict[str, ToolAssignment] = {}

    async def list_tools(self) -> list[ToolItem]:
        snapshot = await store.get_snapshot()
        tools: list[ToolItem] = []
        async with self._lock:
            for item in snapshot.items:
                override = self._overrides.get(item.id)
                if override and not override.enabled:
                    tools.append(item.model_copy(update={"alive": False}))
                else:
                    tools.append(item)
        return tools

    async def set_enabled(self, tool_id: str, enabled: bool) -> None:
        async with self._lock:
            override = self._overrides.setdefault(tool_id, ToolAssignment(tool_id))
            override.enabled = enabled

    async def get_status_map(self) -> Mapping[str, bool]:
        async with self._lock:
            return {tool_id: override.enabled for tool_id, override in self._overrides.items()}

    async def assign(self, agent_id: str, tool_ids: Iterable[str]) -> Mapping[str, list[str]]:
        normalized = {tool_id: set() for tool_id in tool_ids}
        async with self._lock:
            # Clear previous assignments for the agent.
            for override in self._overrides.values():
                override.assigned_agents.discard(agent_id)
            for tool_id in tool_ids:
                override = self._overrides.setdefault(tool_id, ToolAssignment(tool_id))
                override.assigned_agents.add(agent_id)
        return {tool_id: sorted(agents) for tool_id, agents in normalized.items()}

    async def get_assignments(self) -> dict[str, list[str]]:
        async with self._lock:
            return {
                tool_id: sorted(override.assigned_agents)
                for tool_id, override in self._overrides.items()
                if override.assigned_agents
            }

    async def reload(self) -> None:
        await store.refresh(force=True)


runtime_tool_registry = ToolRuntimeRegistry()

__all__ = ["ToolRuntimeRegistry", "runtime_tool_registry"]
