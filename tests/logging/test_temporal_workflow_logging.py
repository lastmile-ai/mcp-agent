import asyncio
from types import SimpleNamespace

import pytest
from temporalio import workflow as temporal_workflow

from mcp_agent.executor.temporal import temporal_context
from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import Logger, LoggingConfig
from mcp_agent.logging.transport import AsyncEventBus


class RecordingUpstreamSession:
    def __init__(self):
        self.calls = []

    async def send_log_message(self, level, data, logger, related_request_id=None):
        self.calls.append(
            {
                "level": level,
                "data": data,
                "logger": logger,
                "related_request_id": related_request_id,
            }
        )


@pytest.fixture
def temporal_harness(monkeypatch):
    AsyncEventBus.reset()
    monkeypatch.setattr(LoggingConfig, "_initialized", False)
    monkeypatch.setattr(LoggingConfig, "_event_filter_ref", None)
    monkeypatch.setattr(LoggingConfig, "_upstream_event_filter_ref", None)
    monkeypatch.setattr(LoggingConfig, "_session_min_levels", {})

    try:
        previous_event_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_event_loop = None

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    scheduled = []
    activity_calls = []
    execution_id = {"value": None}

    monkeypatch.setattr(temporal_workflow, "in_workflow", lambda: True)
    monkeypatch.setattr(
        temporal_workflow,
        "create_task",
        lambda coroutine: scheduled.append(coroutine),
        raising=False,
    )

    async def execute_activity(*args, **kwargs):
        activity_calls.append((args, kwargs))

    monkeypatch.setattr(temporal_workflow, "execute_activity", execute_activity)
    monkeypatch.setattr(
        temporal_context, "get_execution_id", lambda: execution_id["value"]
    )

    def drain():
        while scheduled:
            event_loop.run_until_complete(scheduled.pop(0))

    harness = SimpleNamespace(
        loop=event_loop,
        drain=drain,
        activity_calls=activity_calls,
        execution_id=execution_id,
    )

    try:
        yield harness
    finally:
        for coroutine in scheduled:
            coroutine.close()
        if LoggingConfig._initialized:
            event_loop.run_until_complete(LoggingConfig.shutdown())
        else:
            event_loop.run_until_complete(AsyncEventBus.get().stop())
        pending = [task for task in asyncio.all_tasks(event_loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            event_loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        AsyncEventBus.reset()
        event_loop.close()
        asyncio.set_event_loop(
            previous_event_loop
            if previous_event_loop and not previous_event_loop.is_closed()
            else None
        )


def configure_logging(harness, min_level):
    harness.loop.run_until_complete(
        LoggingConfig.configure(
            event_filter=EventFilter(min_level=min_level),
            progress_display=False,
        )
    )


def test_temporal_workflow_applies_local_log_level(temporal_harness, capsys):
    configure_logging(temporal_harness, "error")
    logger = Logger("tests.temporal")

    logger.debug("hidden debug event")
    temporal_harness.drain()

    assert capsys.readouterr().err == ""

    logger.error("visible error event")
    temporal_harness.drain()

    assert "visible error event" in capsys.readouterr().err


def test_temporal_workflow_applies_upstream_log_level(temporal_harness):
    configure_logging(temporal_harness, "error")
    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal", bound_context=SimpleNamespace(upstream_session=upstream)
    )

    logger.debug("hidden debug event")
    temporal_harness.drain()
    logger.error("visible error event")
    temporal_harness.drain()

    assert [call["data"]["message"] for call in upstream.calls] == [
        "visible error event"
    ]


def test_temporal_workflow_treats_progress_as_info(temporal_harness):
    configure_logging(temporal_harness, "info")
    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal", bound_context=SimpleNamespace(upstream_session=upstream)
    )

    logger.progress("visible progress event")
    temporal_harness.drain()

    assert [(call["level"], call["data"]["message"]) for call in upstream.calls] == [
        ("info", "visible progress event")
    ]


def test_temporal_workflow_applies_activity_log_level(temporal_harness):
    configure_logging(temporal_harness, "error")
    temporal_harness.execution_id["value"] = "execution-1"
    logger = Logger("tests.temporal")

    logger.debug("hidden debug event")
    temporal_harness.drain()
    logger.error("visible error event")
    temporal_harness.drain()

    assert len(temporal_harness.activity_calls) == 1
    assert temporal_harness.activity_calls[0][0][:6] == (
        "mcp_forward_log",
        "execution-1",
        "error",
        "tests.temporal",
        "visible error event",
        {},
    )


@pytest.mark.parametrize(
    ("local_level", "upstream_level", "expected_upstream", "expected_stderr"),
    [
        ("debug", "error", [], "debug event"),
        ("error", "debug", ["debug event"], ""),
    ],
)
def test_temporal_workflow_keeps_local_and_upstream_filters_independent(
    temporal_harness,
    capsys,
    local_level,
    upstream_level,
    expected_upstream,
    expected_stderr,
):
    configure_logging(temporal_harness, local_level)
    LoggingConfig.set_min_level(upstream_level)
    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal", bound_context=SimpleNamespace(upstream_session=upstream)
    )

    logger.debug("debug event")
    temporal_harness.drain()

    assert [call["data"]["message"] for call in upstream.calls] == expected_upstream
    stderr = capsys.readouterr().err
    if expected_stderr:
        assert expected_stderr in stderr
    else:
        assert stderr == ""


def test_temporal_workflow_applies_session_upstream_log_level(temporal_harness, capsys):
    configure_logging(temporal_harness, "debug")
    LoggingConfig.set_session_min_level("session-1", "error")
    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal",
        session_id="session-1",
        bound_context=SimpleNamespace(upstream_session=upstream),
    )

    logger.debug("local debug event")
    temporal_harness.drain()
    logger.error("upstream error event")
    temporal_harness.drain()

    assert [call["data"]["message"] for call in upstream.calls] == [
        "upstream error event"
    ]
    assert "local debug event" in capsys.readouterr().err


@pytest.mark.parametrize("route", ["upstream", "activity", "stderr"])
def test_temporal_workflow_is_silent_before_logging_is_configured(
    temporal_harness, capsys, route
):
    upstream = RecordingUpstreamSession() if route == "upstream" else None
    if route == "activity":
        temporal_harness.execution_id["value"] = "execution-1"
    context = SimpleNamespace(upstream_session=upstream) if upstream else None
    logger = Logger("tests.temporal", bound_context=context)

    logger.error("unconfigured event")
    temporal_harness.drain()

    assert upstream is None or upstream.calls == []
    assert temporal_harness.activity_calls == []
    assert capsys.readouterr().err == ""
