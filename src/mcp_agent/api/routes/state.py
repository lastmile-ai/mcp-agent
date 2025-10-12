"""Shared utilities for public API route modules."""

from __future__ import annotations

import asyncio
import os
from typing import Dict, List, Set, Tuple

import jwt
from starlette.requests import Request

from mcp_agent.artifacts.index import ArtifactIndex
from mcp_agent.feature.intake import FeatureIntakeManager
from mcp_agent.runloop.events import EventBus


class PublicAPIState:
    """Encapsulates all mutable state for the public API."""

    def __init__(self):
        self.runs: Dict[str, Dict] = {}
        self.event_buses: Dict[str, EventBus] = {}
        self.tasks: Set[asyncio.Task] = set()
        self.artifacts: Dict[str, tuple[bytes, str]] = {}
        self.artifact_index = ArtifactIndex()
        self.feature_manager = FeatureIntakeManager(artifact_sink=self.artifacts)

    async def cancel_all_tasks(self):
        """Cancel all tracked background tasks."""

        tasks = list(self.tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        for bus in list(self.event_buses.values()):
            await bus.close()
        self.event_buses.clear()
        await self.feature_manager.close()
        self.feature_manager.reset()

    def clear(self):
        """Clear all state dictionaries."""

        self.runs.clear()
        self.event_buses.clear()
        self.feature_manager.reset()


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
