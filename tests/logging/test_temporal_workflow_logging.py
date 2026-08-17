import asyncio

import pytest
from temporalio import workflow as temporal_workflow

from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.logger import Logger, LoggingConfig
from mcp_agent.logging.transport import AsyncEventBus


@pytest.fixture
def workflow_logger(monkeypatch):
    """A logger that emits through the Temporal workflow branch of Logger._emit_event.

    That branch bypasses the event bus transport, so it has to apply the
    configured logger level itself.
    """
    AsyncEventBus.reset()
    monkeypatch.setattr(temporal_workflow, "in_workflow", lambda: True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        LoggingConfig.configure(
            event_filter=EventFilter(min_level="error"), progress_display=False
        )
    )

    try:
        yield Logger("tests.temporal")
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


def test_workflow_event_below_configured_level_is_dropped(workflow_logger, capsys):
    workflow_logger.debug("debug message from workflow")

    assert capsys.readouterr().err == ""


def test_workflow_event_at_configured_level_is_emitted(workflow_logger, capsys):
    workflow_logger.error("error message from workflow")

    assert "error message from workflow" in capsys.readouterr().err
