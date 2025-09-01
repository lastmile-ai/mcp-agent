from typing import Any, Dict

from temporalio import activity

from mcp_agent.mcp.client_proxy import log_via_proxy, ask_via_proxy
from mcp_agent.core.context_dependent import ContextDependent


class SystemActivities(ContextDependent):
    """Activities used by Temporal workflows to interact with the MCPApp gateway."""

    @activity.defn(name="mcp_forward_log")
    async def forward_log(
        self,
        run_id: str,
        level: str,
        namespace: str,
        message: str,
        data: Dict[str, Any] | None = None,
    ) -> bool:
        registry = self.context.server_registry
        return await log_via_proxy(
            registry,
            run_id=run_id,
            level=level,
            namespace=namespace,
            message=message,
            data=data or {},
        )

    @activity.defn(name="mcp_request_user_input")
    async def request_user_input(
        self,
        session_id: str,
        workflow_id: str,
        run_id: str,
        prompt: str,
        signal_name: str = "human_input",
    ) -> Dict[str, Any]:
        # Reuse proxy ask API; returns {result} or {error}
        registry = self.context.server_registry
        return await ask_via_proxy(
            registry,
            run_id=run_id,
            prompt=prompt,
            metadata={
                "session_id": session_id,
                "workflow_id": workflow_id,
                "signal_name": signal_name,
            },
        )
