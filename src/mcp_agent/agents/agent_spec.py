from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class AgentSpec(BaseModel):
    """
    Canonical, strongly-typed Agent specification used across the system.

    This represents a declarative way to define an Agent without constructing it yet.
    AgentSpec is used to create an Agent instance.
    It can be defined as a config (loaded from a md, yaml, json, etc.), or
    it can be created programmatically.
    """

    name: str
    """
    The name of the agent.
    """

    instruction: str | None = None
    """
    The instruction of the agent.
    """

    server_names: List[str] = Field(default_factory=list)
    """
    The names of MCP servers that the agent has access to.
    """

    connection_persistence: bool = True
    """
    Whether to persist connections to the MCP servers.
    """

    # NOTE: A human_input_callback can be programmatically specified
    # and will be used by the AgentSpec. However, since it is
    # not a JSON-serializable object, it cannot be set via configuration.
    # human_input_callback: Optional[Callable] = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
