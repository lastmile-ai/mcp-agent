import asyncio

from types import SimpleNamespace

import pytest
from temporalio import workflow as temporal_workflow

from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import Logger, LoggingConfig
from mcp_agent.logging.transport import AsyncEventBus


class RecordingUpstreamSession:
    def __init__(self):
        self.calls = []

    async def send_log_message(self, level, data, logger, related_request_id=None):
        self.calls.append({"level": level, "data": data, "logger": logger})


@pytest.fixture
def workflow_loop(monkeypatch):
    """Make Logger._emit_event take its Temporal workflow branch.

    That branch is chosen when no loop is running, and it forwards events
    without going through the event bus.
    """
    AsyncEventBus.reset()
    monkeypatch.setattr(temporal_workflow, "in_workflow", lambda: True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        yield loop
    finally:
        loop.run_until_complete(LoggingConfig.shutdown())
        pending = asyncio.all_tasks(loop)
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.wait(pending))
        asyncio.set_event_loop(None)
        loop.close()
        AsyncEventBus.reset()


def configure_logging(loop, level):
    loop.run_until_complete(
        LoggingConfig.configure(
            event_filter=EventFilter(min_level=level), progress_display=False
        )
    )


@pytest.fixture
def scheduled_workflow_tasks(monkeypatch):
    """Collect the coroutines the workflow branch hands to Temporal.

    Tests run them explicitly so they can observe which destination the event
    was forwarded to.
    """
    scheduled = []
    monkeypatch.setattr(
        temporal_workflow, "create_task", scheduled.append, raising=False
    )
    return scheduled


def test_workflow_event_below_configured_level_is_dropped(workflow_loop, capsys):
    configure_logging(workflow_loop, "error")

    Logger("tests.temporal").debug("debug message from workflow")

    assert capsys.readouterr().err == ""


def test_workflow_event_at_configured_level_is_emitted(workflow_loop, capsys):
    configure_logging(workflow_loop, "error")

    Logger("tests.temporal").error("error message from workflow")

    assert "error message from workflow" in capsys.readouterr().err


def test_workflow_event_below_upstream_level_is_not_forwarded(
    workflow_loop, scheduled_workflow_tasks, capsys
):
    configure_logging(workflow_loop, "debug")
    LoggingConfig.set_min_level("error")

    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal", bound_context=SimpleNamespace(upstream_session=upstream)
    )
    logger.debug("debug message from workflow")

    for coro in scheduled_workflow_tasks:
        workflow_loop.run_until_complete(coro)

    assert upstream.calls == []
    assert "debug message from workflow" in capsys.readouterr().err


def test_workflow_event_at_upstream_level_is_forwarded(
    workflow_loop, scheduled_workflow_tasks, capsys
):
    configure_logging(workflow_loop, "error")
    LoggingConfig.set_min_level("debug")

    upstream = RecordingUpstreamSession()
    logger = Logger(
        "tests.temporal", bound_context=SimpleNamespace(upstream_session=upstream)
    )
    logger.debug("debug message from workflow")

    for coro in scheduled_workflow_tasks:
        workflow_loop.run_until_complete(coro)

    assert [call["level"] for call in upstream.calls] == ["debug"]
    assert capsys.readouterr().err == ""
