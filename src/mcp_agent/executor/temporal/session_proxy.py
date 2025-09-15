from __future__ import annotations

from typing import Any, Dict, List, Type
import asyncio

import anyio
import mcp.types as types
from anyio.streams.memory import (
    MemoryObjectReceiveStream,
    MemoryObjectSendStream,
)
from temporalio import workflow as _twf

from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.shared.message import ServerMessageMetadata

from mcp_agent.core.context import Context
from mcp_agent.executor.temporal.system_activities import SystemActivities
from mcp_agent.executor.temporal.temporal_context import get_execution_id


class SessionProxy(ServerSession):
    """
    SessionProxy acts like an MCP `ServerSession` for code running under the
    Temporal engine. It forwards server->client messages through the MCPApp
    gateway so that logs, notifications, and requests reach the original
    upstream MCP client.

    Behavior:
    - Inside a Temporal workflow (deterministic scope), all network I/O is
      performed via registered Temporal activities.
    - Outside a workflow (e.g., inside an activity or plain asyncio code),
      calls are executed directly using the SystemActivities helpers.

    This keeps workflow logic deterministic while remaining a drop-in proxy
    for the common ServerSession methods used by the agent runtime.
    """

    def __init__(self, *, executor, context: Context) -> None:
        # Create inert in-memory streams to satisfy base constructor. We do not
        # use these streams; all communication is proxied via HTTP gateway.
        send_read, recv_read = anyio.create_memory_object_stream(0)
        send_write, recv_write = anyio.create_memory_object_stream(0)

        init_opts = InitializationOptions(
            server_name="mcp_agent_proxy",
            server_version="0.0.0",
            capabilities=types.ServerCapabilities(),
            instructions=None,
        )
        # Initialize base class in stateless mode to skip handshake state
        super().__init__(
            recv_read,  # type: ignore[arg-type]
            send_write,  # type: ignore[arg-type]
            init_opts,
            stateless=True,
        )

        # Keep references so streams aren't GC'd
        self._dummy_streams: tuple[
            MemoryObjectSendStream[Any],
            MemoryObjectReceiveStream[Any],
            MemoryObjectSendStream[Any],
            MemoryObjectReceiveStream[Any],
        ] = (send_read, recv_read, send_write, recv_write)

        self._executor = executor
        self._context = context
        # Local helper used when we're not inside a workflow runtime
        self._system_activities = SystemActivities(context)
        # Provide a low-level RPC facade similar to real ServerSession
        self.rpc = _RPC(self)

    # ----------------------
    # Generic passthroughs
    # ----------------------
    async def notify(self, method: str, params: Dict[str, Any] | None = None) -> bool:
        """Send a server->client notification via the gateway.

        Returns True on best-effort success.
        """
        exec_id = get_execution_id()
        if not exec_id:
            return False

        if _in_workflow_runtime():
            try:
                act = self._context.task_registry.get_activity("mcp_relay_notify")
                await self._executor.execute(
                    act,
                    exec_id,
                    method,
                    params or {},
                )
                return True
            except Exception:
                return False
        # Non-workflow (activity/asyncio): fire-and-forget best-effort
        try:
            asyncio.create_task(
                self._system_activities.relay_notify(exec_id, method, params or {})
            )
        except Exception:
            pass
        return True

    async def request(
        self, method: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Send a server->client request and return the client's response.
        The result is a plain JSON-serializable dict.
        """
        exec_id = get_execution_id()
        if not exec_id:
            return {"error": "missing_execution_id"}

        if _in_workflow_runtime():
            act = self._context.task_registry.get_activity("mcp_relay_request")
            return await self._executor.execute(
                act,
                exec_id,
                method,
                params or {},
            )
        return await self._system_activities.relay_request(
            exec_id, method, params or {}
        )

    async def send_notification(
        self,
        notification: types.ServerNotification,
        related_request_id: types.RequestId | None = None,
    ) -> None:
        root = notification.root
        params: Dict[str, Any] | None = None
        try:
            if getattr(root, "params", None) is not None:
                params = root.params.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
            else:
                params = {}
        except Exception:
            params = {}
        # Best-effort pass-through of related_request_id when provided
        if related_request_id is not None:
            params = dict(params or {})
            params["related_request_id"] = related_request_id
        await self.notify(root.method, params)  # type: ignore[attr-defined]

    async def send_request(
        self,
        request: types.ServerRequest,
        result_type: Type[Any],
        metadata: ServerMessageMetadata | None = None,
    ) -> Any:
        root = request.root
        params: Dict[str, Any] | None = None
        try:
            if getattr(root, "params", None) is not None:
                params = root.params.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
            else:
                params = {}
        except Exception:
            params = {}
        # Note: metadata (e.g., related_request_id) is handled server-side where applicable
        payload = await self.request(root.method, params)  # type: ignore[attr-defined]
        # Attempt to validate into the requested result type
        try:
            return result_type.model_validate(payload)  # type: ignore[attr-defined]
        except Exception:
            return payload

    async def send_log_message(
        self,
        level: types.LoggingLevel,
        data: Any,
        logger: str | None = None,
        related_request_id: types.RequestId | None = None,
    ) -> None:
        """Best-effort log forwarding to the client's UI."""
        # Prefer activity-based forwarding inside workflow for determinism
        exec_id = get_execution_id()
        if _in_workflow_runtime() and exec_id:
            try:
                act = self._context.task_registry.get_activity("mcp_forward_log")
                namespace = (
                    (data or {}).get("namespace")
                    if isinstance(data, dict)
                    else (logger or "mcp_agent")
                )
                message = (data or {}).get("message") if isinstance(data, dict) else ""
                await self._executor.execute(
                    act,
                    exec_id,
                    str(level),
                    namespace or (logger or "mcp_agent"),
                    message or "",
                    (data or {}),
                )
                return
            except Exception:
                # Fall back to notify path below
                pass

        params: Dict[str, Any] = {"level": str(level), "data": data, "logger": logger}
        if related_request_id is not None:
            params["related_request_id"] = related_request_id
        await self.notify("notifications/message", params)

    async def send_progress_notification(
        self,
        progress_token: str | int,
        progress: float,
        total: float | None = None,
        message: str | None = None,
        related_request_id: str | None = None,
    ) -> None:
        params: Dict[str, Any] = {
            "progressToken": progress_token,
            "progress": progress,
        }
        if total is not None:
            params["total"] = total
        if message is not None:
            params["message"] = message
        if related_request_id is not None:
            params["related_request_id"] = related_request_id
        await self.notify("notifications/progress", params)

    async def send_resource_updated(self, uri: types.AnyUrl) -> None:
        await self.notify("notifications/resources/updated", {"uri": str(uri)})

    async def send_resource_list_changed(self) -> None:
        await self.notify("notifications/resources/list_changed", {})

    async def send_tool_list_changed(self) -> None:
        await self.notify("notifications/tools/list_changed", {})

    async def send_prompt_list_changed(self) -> None:
        await self.notify("notifications/prompts/list_changed", {})

    async def send_ping(self) -> types.EmptyResult:
        result = await self.request("ping", {})
        return types.EmptyResult.model_validate(result)

    async def list_roots(self) -> types.ListRootsResult:
        result = await self.request("roots/list", {})
        return types.ListRootsResult.model_validate(result)

    async def create_message(
        self,
        messages: List[types.SamplingMessage],
        *,
        max_tokens: int,
        system_prompt: str | None = None,
        include_context: types.IncludeContext | None = None,
        temperature: float | None = None,
        stop_sequences: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        model_preferences: types.ModelPreferences | None = None,
        related_request_id: types.RequestId | None = None,
    ) -> types.CreateMessageResult:
        params: Dict[str, Any] = {
            "messages": [m.model_dump(by_alias=True, mode="json") for m in messages],
            "maxTokens": max_tokens,
        }
        if system_prompt is not None:
            params["systemPrompt"] = system_prompt
        if include_context is not None:
            params["includeContext"] = include_context
        if temperature is not None:
            params["temperature"] = temperature
        if stop_sequences is not None:
            params["stopSequences"] = stop_sequences
        if metadata is not None:
            params["metadata"] = metadata
        if model_preferences is not None:
            params["modelPreferences"] = model_preferences.model_dump(
                by_alias=True, mode="json"
            )
        if related_request_id is not None:
            # Threading ID through JSON-RPC metadata is handled by gateway; include for completeness
            params["related_request_id"] = related_request_id

        result = await self.request("sampling/createMessage", params)
        try:
            return types.CreateMessageResult.model_validate(result)
        except Exception as e:
            raise RuntimeError(f"sampling/createMessage returned invalid result: {e}")

    async def elicit(
        self,
        message: str,
        requestedSchema: types.ElicitRequestedSchema,
        related_request_id: types.RequestId | None = None,
    ) -> types.ElicitResult:
        params: Dict[str, Any] = {
            "message": message,
            "requestedSchema": requestedSchema,
        }
        if related_request_id is not None:
            params["related_request_id"] = related_request_id
        result = await self.request("elicitation/create", params)
        try:
            return types.ElicitResult.model_validate(result)
        except Exception as e:
            raise RuntimeError(f"elicitation/create returned invalid result: {e}")


def _in_workflow_runtime() -> bool:
    """Return True if currently executing inside a Temporal workflow sandbox."""
    try:
        return _twf.in_workflow()
    except Exception:
        return False


class _RPC:
    """Lightweight facade to mimic the low-level RPC interface on sessions."""

    def __init__(self, proxy: SessionProxy) -> None:
        self._proxy = proxy

    async def notify(self, method: str, params: Dict[str, Any] | None = None) -> None:
        await self._proxy.notify(method, params or {})

    async def request(
        self, method: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        return await self._proxy.request(method, params or {})
