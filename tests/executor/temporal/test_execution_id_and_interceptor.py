import pytest
from unittest.mock import patch


@pytest.mark.asyncio
@patch("temporalio.workflow.info")
@patch("temporalio.workflow.in_workflow", return_value=True)
def test_get_execution_id_in_workflow(_mock_in_wf, mock_info):
    from mcp_agent.executor.temporal.temporal_context import get_execution_id

    mock_info.return_value.run_id = "run-123"
    assert get_execution_id() == "run-123"


@pytest.mark.asyncio
@patch("temporalio.activity.info")
def test_get_execution_id_in_activity(mock_act_info):
    from mcp_agent.executor.temporal.temporal_context import get_execution_id

    mock_act_info.return_value.workflow_run_id = "run-aaa"
    assert get_execution_id() == "run-aaa"


def test_interceptor_restores_prev_value():
    from mcp_agent.executor.temporal.interceptor import context_from_header
    from mcp_agent.executor.temporal.temporal_context import (
        EXECUTION_ID_KEY,
        set_execution_id,
        get_execution_id,
    )
    import temporalio.converter

    payload_converter = temporalio.converter.default().payload_converter

    class Input:
        headers = {}

    set_execution_id("prev")
    input = Input()
    # simulate header with new value
    input.headers[EXECUTION_ID_KEY] = payload_converter.to_payload("new")

    assert get_execution_id() == "prev"
    with context_from_header(input, payload_converter):
        # inside scope we should get header value
        assert get_execution_id() == "new"
    # restored
    assert get_execution_id() == "prev"


@pytest.mark.asyncio
async def test_http_proxy_helpers_happy_and_error_paths(monkeypatch):
    from mcp_agent.mcp import client_proxy

    class Resp:
        def __init__(self, status_code, json_data=None, text=""):
            self.status_code = status_code
            self._json = json_data or {}
            self.text = text
            self.content = b"x" if json_data is not None else b""

        def json(self):
            return self._json

    class Client:
        def __init__(self, rcodes_iter):
            self._rcodes = rcodes_iter

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            code, body = next(self._rcodes)
            if body is None:
                return Resp(code)
            return Resp(code, body)

    # log_via_proxy ok, then error
    rcodes = iter(
        [
            (200, {"ok": True}),
            (500, None),
            (200, {"ok": True}),
            (401, None),
            (200, {"ok": True}),
            (400, None),
        ]
    )

    monkeypatch.setattr(
        client_proxy.httpx, "AsyncClient", lambda timeout: Client(rcodes)
    )

    ok = await client_proxy.log_via_proxy("run", "info", "ns", "msg")
    assert ok is True
    ok = await client_proxy.log_via_proxy("run", "info", "ns", "msg")
    assert ok is False

    # notify ok, then error
    ok = await client_proxy.notify_via_proxy("run", "m", {})
    assert ok is True
    ok = await client_proxy.notify_via_proxy("run", "m", {})
    assert ok is False

    # request ok, then error
    res = await client_proxy.request_via_proxy("run", "m", {})
    assert isinstance(res, dict) and res.get("ok", True) in (True,)
    res = await client_proxy.request_via_proxy("run", "m", {})
    assert isinstance(res, dict) and "error" in res
