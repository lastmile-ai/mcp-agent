"""
Events and event filters for the logger module for the MCP Agent
"""

import logging
import random

from datetime import datetime
from typing import (
    Any,
    Dict,
    Literal,
    Set,
)

from pydantic import BaseModel, ConfigDict, Field


EventType = Literal["debug", "info", "warning", "error", "progress"]
"""Broad categories for events (severity or role)."""


class EventContext(BaseModel):
    """
    Stores correlation or cross-cutting data (workflow IDs, user IDs, etc.).
    Also used for distributed environments or advanced logging.
    """

    session_id: str | None = None
    workflow_id: str | None = None
    # request_id: Optional[str] = None
    # parent_event_id: Optional[str] = None
    # correlation_id: Optional[str] = None
    # user_id: Optional[str] = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class Event(BaseModel):
    """
    Core event structure. Allows both a broad 'type' (EventType)
    and a more specific 'name' string for domain-specific labeling (e.g. "ORDER_PLACED").
    """

    type: EventType
    name: str | None = None
    namespace: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Dict[str, Any] = Field(default_factory=dict)
    context: EventContext | None = None

    # Runtime-only handle for upstream forwarding. Present for listeners to
    # use, explicitly excluded from any serialization/dumps.
    upstream_session: Any | None = Field(default=None, exclude=True)

    # For distributed tracing
    span_id: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class EventFilter(BaseModel):
    """
    Filter events by:
      - allowed EventTypes (types)
      - allowed event 'names'
      - allowed namespace prefixes
      - a minimum severity level (DEBUG < INFO < WARNING < ERROR)
    """

    types: Set[EventType] | None = Field(default_factory=set)
    names: Set[str] | None = Field(default_factory=set)
    namespaces: Set[str] | None = Field(default_factory=set)
    min_level: EventType | None = "debug"

    def matches(self, event: Event) -> bool:
        """
        Check if an event matches this EventFilter criteria.
        """
        # 1) Filter by broad event type
        if self.types:
            if event.type not in self.types:
                return False

        # 2) Filter by custom event name
        if self.names:
            if not event.name or event.name not in self.names:
                return False

        # 3) Filter by namespace prefix
        if self.namespaces and not any(
            event.namespace.startswith(ns) for ns in self.namespaces
        ):
            return False

        # 4) Minimum severity
        if self.min_level:
            level_map: Dict[EventType, int] = {
                "debug": logging.DEBUG,
                "info": logging.INFO,
                "warning": logging.WARNING,
                "error": logging.ERROR,
            }

            min_val = level_map.get(self.min_level, logging.DEBUG)
            event_val = level_map.get(event.type, logging.DEBUG)
            if event_val < min_val:
                return False

        return True


class SamplingFilter(EventFilter):
    """
    Random sampling on top of base filter.
    Only pass an event if it meets the base filter AND random() < sample_rate.
    """

    sample_rate: float = 0.1
    """Fraction of events to pass through"""

    def matches(self, event: Event) -> bool:
        if not super().matches(event):
            return False
        return random.random() < self.sample_rate
