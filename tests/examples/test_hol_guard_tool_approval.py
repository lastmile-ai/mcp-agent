import importlib.util
from pathlib import Path

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams

EXAMPLE_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "basic"
    / "hol_guard_tool_approval"
    / "hol_guard_llm.py"
)

spec = importlib.util.spec_from_file_location("hol_guard_llm", EXAMPLE_PATH)
assert spec is not None
hol_guard_llm = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(hol_guard_llm)

HolGuardToolApprovalMixin = hol_guard_llm.HolGuardToolApprovalMixin
_is_allowed = hol_guard_llm._is_allowed


def call_tool_request() -> CallToolRequest:
    return CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="filesystem_write",
            arguments={"path": "/tmp/demo.txt", "content": "hello"},
        ),
    )


@pytest.mark.parametrize(
    "decision",
    [
        {"decision": "allow"},
        {"decision": "ALLOWED"},
        {"allow": True},
    ],
)
def test_hol_guard_allows_only_explicit_safe_results(decision):
    assert _is_allowed(decision)


@pytest.mark.parametrize(
    "decision",
    [
        {"decision": "deny"},
        {"decision": "review"},
        {"allow": False},
        {"unexpected": "shape"},
    ],
)
def test_hol_guard_fails_closed_for_non_allow_results(decision):
    assert not _is_allowed(decision)


@pytest.mark.asyncio
async def test_pre_tool_call_returns_request_when_guard_allows():
    llm = object.__new__(HolGuardToolApprovalMixin)
    seen_payloads = []

    def allow(payload):
        seen_payloads.append(payload)
        return {"decision": "allow"}

    llm.guard_runner = allow
    request = call_tool_request()

    result = await llm.pre_tool_call("tool-call-1", request)

    assert result is request
    assert seen_payloads == [
        {
            "tool_call_id": "tool-call-1",
            "tool_name": "filesystem_write",
            "arguments": {"path": "/tmp/demo.txt", "content": "hello"},
        }
    ]


@pytest.mark.asyncio
async def test_pre_tool_call_blocks_denied_tools():
    llm = object.__new__(HolGuardToolApprovalMixin)
    llm.guard_runner = lambda payload: {"decision": "deny"}

    result = await llm.pre_tool_call("tool-call-2", call_tool_request())

    assert result is False


@pytest.mark.asyncio
async def test_pre_tool_call_fails_closed_when_guard_errors():
    llm = object.__new__(HolGuardToolApprovalMixin)

    def raise_guard_error(payload):
        raise RuntimeError("guard unavailable")

    llm.guard_runner = raise_guard_error

    result = await llm.pre_tool_call("tool-call-3", call_tool_request())

    assert result is False
