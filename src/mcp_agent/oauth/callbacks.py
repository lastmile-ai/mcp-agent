"""Callback coordination for delegated OAuth flows."""

from __future__ import annotations

import asyncio
from typing import Any, Dict


class OAuthCallbackRegistry:
    """Manage asynchronous delivery of OAuth authorization callbacks."""

    def __init__(self) -> None:
        self._pending: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        # Map OAuth state -> flow_id to support loopback callbacks that
        # only receive the state param (no flow id in the redirect path).
        self._state_to_flow: Dict[str, str] = {}

    async def create_handle(self, flow_id: str) -> asyncio.Future[Dict[str, Any]]:
        """Create (or reuse) a future associated with a flow identifier."""
        async with self._lock:
            future = self._pending.get(flow_id)
            if future is None or future.done():
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._pending[flow_id] = future
            return future

    async def deliver(self, flow_id: str, payload: Dict[str, Any]) -> bool:
        """Set the result for a pending flow, returning False when no listener exists."""
        async with self._lock:
            future = self._pending.get(flow_id)
            if future is None:
                # print all entries in _pending for debugging
                return False
            if not future.done():
                future.set_result(payload)
            return True

    async def register_state(self, flow_id: str, state: str) -> None:
        """Associate an OAuth state value with a flow id for loopback delivery."""
        if not state:
            return
        async with self._lock:
            self._state_to_flow[state] = flow_id

    async def deliver_by_state(self, state: str, payload: Dict[str, Any]) -> bool:
        """Deliver a callback payload by resolving the flow id from state.

        Returns False if the state is unknown.
        """
        if not state:
            return False
        async with self._lock:
            flow_id = self._state_to_flow.pop(state, None)
        if not flow_id:
            return False
        return await self.deliver(flow_id, payload)

    async def fail(self, flow_id: str, exc: Exception) -> bool:
        async with self._lock:
            future = self._pending.get(flow_id)
            if future is None:
                return False
            if not future.done():
                future.set_exception(exc)
            return True

    async def discard(self, flow_id: str) -> None:
        async with self._lock:
            future = self._pending.pop(flow_id, None)
            if future and not future.done():
                future.cancel()
            # Best-effort cleanup of any state entries pointing to this flow
            for s, f in list(self._state_to_flow.items()):
                if f == flow_id:
                    self._state_to_flow.pop(s, None)


# Global registry used by server + flow coordinator
callback_registry = OAuthCallbackRegistry()
