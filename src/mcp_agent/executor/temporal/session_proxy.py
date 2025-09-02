from __future__ import annotations

from typing import Any, Dict, Optional


class SessionProxy:
    """
    A 'virtual' MCP ServerSession bound to a Temporal workflow run.

    This proxy exposes a subset of the ServerSession API and routes calls
    through generic Temporal activities to keep workflow code deterministic.

    Methods:
        - send_log_message(level, data, logger=None, related_request_id=None)
        - notify(method, params)
        - request(method, params)
    """

    def __init__(self, *, executor, run_id: str):
        self._executor = executor
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        return self._run_id

    async def send_log_message(
        self,
        *,
        level: str,
        data: Dict[str, Any] | Any,
        logger: Optional[str] = None,
        related_request_id: Optional[str] = None,
    ) -> None:
        # Map to notifications/message via generic relay
        params: Dict[str, Any] = {
            "level": level,
            "data": data,
            "logger": logger,
        }
        if related_request_id is not None:
            params["related_request_id"] = related_request_id

        activity = self._executor.context.task_registry.get_activity("mcp_relay_notify")
        await self._executor.execute(
            activity, self._run_id, "notifications/message", params
        )

    async def notify(self, method: str, params: Dict[str, Any] | None = None) -> bool:
        activity = self._executor.context.task_registry.get_activity("mcp_relay_notify")
        result = await self._executor.execute(
            activity, self._run_id, method, params or {}
        )
        return bool(result)

    async def request(
        self, method: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        activity = self._executor.context.task_registry.get_activity(
            "mcp_relay_request"
        )
        return await self._executor.execute(
            activity, self._run_id, method, params or {}
        )
