import types

import pytest

from mcp_agent.core.context import Context
from mcp_agent.core.request_context import get_current_request_context
from mcp_agent.executor.temporal import session_proxy as sp_module


class _StubSystemActivities:
    def __init__(self) -> None:
        self.last_context = None

    async def relay_request(self, async_mode, execution_id, method, params):
        self.last_context = get_current_request_context()
        return {"ok": True}

    async def relay_notify(self, execution_id, method, params):
        self.last_context = get_current_request_context()
        return True


class _RecordingExecutor:
    def __init__(self) -> None:
        self.contexts: list[Context | None] = []

    async def execute(self, *args, **kwargs):
        self.contexts.append(get_current_request_context())
        return True


@pytest.mark.asyncio
async def test_session_proxy_request_activates_context(monkeypatch):
    ctx = Context()
    stub_activities = _StubSystemActivities()

    monkeypatch.setattr(sp_module, "SystemActivities", lambda context: stub_activities)
    monkeypatch.setattr(sp_module, "get_execution_id", lambda: "exec-request")

    proxy = sp_module.SessionProxy(executor=_RecordingExecutor(), context=ctx)
    result = await proxy.request("mcp.test/request", {"foo": "bar"})

    assert result == {"ok": True}
    assert stub_activities.last_context is ctx


@pytest.mark.asyncio
async def test_session_proxy_notify_activates_context(monkeypatch):
    ctx = Context()
    ctx.task_registry = types.SimpleNamespace(get_activity=lambda name: name)

    stub_executor = _RecordingExecutor()

    monkeypatch.setattr(
        sp_module, "SystemActivities", lambda context: _StubSystemActivities()
    )
    monkeypatch.setattr(sp_module, "get_execution_id", lambda: "exec-notify")
    monkeypatch.setattr(sp_module, "_in_workflow_runtime", lambda: True)

    proxy = sp_module.SessionProxy(executor=stub_executor, context=ctx)
    success = await proxy.notify("notifications/message", {"message": "ping"})

    assert success is True
    assert stub_executor.contexts[-1] is ctx
