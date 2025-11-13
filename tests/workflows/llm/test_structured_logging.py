import pytest
from unittest.mock import MagicMock

from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    TextContent,
)

from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams
from mcp_agent.tracing.trace_store import TraceStore


class DummyAgent:
    def __init__(self, context, result):
        self.name = "dummy-agent"
        self.context = context
        self._result = result
        self.instruction = ""

    async def call_tool(self, name, arguments, server_name=None):
        return self._result


class DummyContext:
    def __init__(self, include_payloads=True):
        logger_config = MagicMock()
        logger_config.include_llm_payloads = include_payloads
        self.config = MagicMock()
        self.config.logger = logger_config
        self.executor = MagicMock()
        self.session_id = "session-123"
        self.model_selector = None
        self.tracing_enabled = False
        self.trace_store = TraceStore()
        self.current_run_id = None


class DummyLLM(AugmentedLLM[str, str]):
    provider = "dummy"

    async def generate(self, message, request_params: RequestParams | None = None):
        return []

    async def generate_str(
        self, message, request_params: RequestParams | None = None
    ) -> str:
        return ""

    async def generate_structured(
        self,
        message,
        response_model,
        request_params: RequestParams | None = None,
    ):
        return response_model()


@pytest.mark.asyncio
async def test_call_tool_emits_tool_events():
    context = DummyContext()
    result = CallToolResult(content=[TextContent(type="text", text="ok")])
    agent = DummyAgent(context, result)
    llm = DummyLLM(agent=agent, context=context)
    llm.logger = MagicMock()

    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="test_tool", arguments={"alpha": 1}),
    )

    context.current_run_id = "trace-run"
    context.trace_store.start_run("trace-run", workflow_name="dummy")
    await llm.call_tool(request)
    context.current_run_id = None

    logged_events = [call.kwargs["data"] for call in llm.logger.info.call_args_list]
    assert logged_events[0]["event_type"] == "tool_request"
    assert logged_events[0]["tool_name"] == "test_tool"
    assert logged_events[1]["event_type"] == "tool_result"
    assert logged_events[1]["result"]["isError"] is False

    trace = context.trace_store.get_run("trace-run")
    assert trace is not None
    assert [event.event_type for event in trace.events] == [
        "tool_request",
        "tool_result",
    ]


def test_payload_redaction():
    context = DummyContext(include_payloads=False)
    agent = DummyAgent(context, CallToolResult(content=[]))
    llm = DummyLLM(agent=agent, context=context)
    llm.logger = MagicMock()

    llm._emit_llm_event(
        "llm_request",
        {"messages": ["hello"], "request": {"foo": "bar"}},
        sensitive_fields=("messages", "request"),
    )

    event = llm.logger.info.call_args.kwargs["data"]
    assert event["messages"] == "[omitted]"
    assert event["request"] == "[omitted]"


def test_sanitize_truncates_large_payloads():
    context = DummyContext()
    result = CallToolResult(content=[TextContent(type="text", text="ok")])
    agent = DummyAgent(context, result)
    llm = DummyLLM(agent=agent, context=context)

    long_text = "x" * 6000
    sanitized = llm._sanitize_for_logging({"text": long_text})
    assert "truncated" in sanitized["text"]
    assert len(sanitized["text"]) < len(long_text)

    long_list = list(range(100))
    sanitized_list = llm._sanitize_for_logging(long_list)
    assert isinstance(sanitized_list, list)
    assert sanitized_list[0].startswith("[omitted ")
    assert len(sanitized_list) == llm._structured_logging_max_collection_items + 1
    assert sanitized_list[-1] == long_list[-1]

    big_dict = {f"key{i}": i for i in range(70)}
    sanitized_dict = llm._sanitize_for_logging(big_dict)
    assert "__truncated__" in sanitized_dict
    assert sanitized_dict["__truncated__"].startswith("[omitted ")
