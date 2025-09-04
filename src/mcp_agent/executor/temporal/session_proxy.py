from typing import Any, Dict, Optional

from mcp_agent.core.context import Context
from mcp_agent.executor.temporal.system_activities import SystemActivities


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

    def __init__(self, *, executor, execution_id: str, context: Context):
        self._executor = executor
        self._execution_id = execution_id
        self.sys_acts = SystemActivities(context)

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @execution_id.setter
    def execution_id(self, value: str):
        self._execution_id = value

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

        # We are outside of the temporal loop. So even though we'd like to do something like
        # result = await self._executor.execute(self.sys_acts.relay_notify, self.execution_id, "notifications/message", params)
        # we can't.
        await self.sys_acts.relay_notify(
            self.execution_id, "notifications/message", params
        )

    async def notify(self, method: str, params: Dict[str, Any] | None = None) -> bool:
        result = await self.sys_acts.relay_notify(
            self.execution_id, method, params or {}
        )
        return bool(result)

    async def request(
        self, method: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        await self.sys_acts.relay_request(self.execution_id, method, params or {})
