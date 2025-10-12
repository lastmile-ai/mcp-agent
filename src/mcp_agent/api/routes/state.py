"""Shared utilities for public API route modules."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Set, Tuple

import jwt
from starlette.requests import Request

from mcp_agent.artifacts.index import ArtifactIndex
from mcp_agent.feature.intake import FeatureIntakeManager
from mcp_agent.llm.events import LLMEventFanout
from mcp_agent.runloop.events import EventBus
from mcp_agent.api.events_sse import RunEventStream


class PublicAPIState:
    """Encapsulates all mutable state for the public API."""

    def __init__(self):
        self.runs: Dict[str, Dict] = {}
        self.event_buses: Dict[str, EventBus] = {}
        self.tasks: Set[asyncio.Task] = set()
        self.artifacts: Dict[str, tuple[bytes, str]] = {}
        self.artifact_index = ArtifactIndex()
        self.feature_manager = FeatureIntakeManager(artifact_sink=self.artifacts)
        self.llm_streams: Dict[str, LLMEventFanout] = {}
        self.run_streams: Dict[str, RunEventStream] = {}
        self.run_lifecycles: Dict[str, Any] = {}
        self.run_cancel_events: Dict[str, asyncio.Event] = {}
        self.run_tasks: Dict[str, asyncio.Task] = {}

    async def cancel_all_tasks(self):
        """Cancel all tracked background tasks."""

        for cancel in self.run_cancel_events.values():
            cancel.set()
        tasks = list(self.tasks)
        tasks.extend(task for task in self.run_tasks.values() if task not in tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.run_tasks.clear()
        for bus in list(self.event_buses.values()):
            await bus.close()
        self.event_buses.clear()
        for stream in list(self.run_streams.values()):
            await stream.close()
        self.run_streams.clear()
        self.run_lifecycles.clear()
        self.run_cancel_events.clear()
        for fanout in list(self.llm_streams.values()):
            await fanout.close()
        self.llm_streams.clear()
        await self.feature_manager.close()
        self.feature_manager.reset()

    def clear(self):
        """Clear all state dictionaries."""

        self.runs.clear()
        self.event_buses.clear()
        self.llm_streams.clear()
        self.run_streams.clear()
        self.run_lifecycles.clear()
        self.run_cancel_events.clear()
        self.run_tasks.clear()
        self.feature_manager.reset()

    def ensure_llm_stream(self, run_id: str) -> LLMEventFanout:
        """Get or create the LLM fan-out for the given run."""

        fanout = self.llm_streams.get(run_id)
        if fanout is None:
            fanout = LLMEventFanout()
            self.llm_streams[run_id] = fanout
        return fanout


def _env_list(name: str) -> List[str]:
    val = os.getenv(name, "")
    return [s.strip() for s in val.split(",") if s.strip()]


def authenticate_request(request: Request) -> Tuple[bool, str]:
    api_keys = set(_env_list("STUDIO_API_KEYS"))
    key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if key and key in api_keys:
        return True, "api_key"
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        hs = os.getenv("JWT_HS256_SECRET")
        if hs:
            try:
                jwt.decode(token, hs, algorithms=["HS256"], options={"verify_aud": False})
                return True, "jwt_hs256"
            except Exception:
                pass
        pub = os.getenv("JWT_PUBLIC_KEY_PEM")
        if pub:
            try:
                jwt.decode(token, pub, algorithms=["RS256"], options={"verify_aud": False})
                return True, "jwt_rs256"
            except Exception:
                pass
    return False, "unauthorized"


def get_public_state(request: Request) -> PublicAPIState:
    """Get the request-scoped :class:`PublicAPIState`."""

    return request.state.public_api_state


__all__ = ["PublicAPIState", "authenticate_request", "get_public_state"]
