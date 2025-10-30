import asyncio

import pytest

from mcp_agent.core.context import Context
from mcp_agent.core.request_context import (
    get_current_request_context,
    reset_current_request_context,
    set_current_request_context,
)
from mcp_agent.logging.events import Event, EventContext
from mcp_agent.logging.listeners import MCPUpstreamLoggingListener
from mcp_agent.logging.logger import (
    LoggingConfig,
    get_logger,
    set_default_bound_context,
)
from mcp_agent.server import app_server


class _DummySession:
    def __init__(self) -> None:
        self.messages: list[tuple] = []

    async def send_log_message(self, level, data, logger=None, related_request_id=None):
        self.messages.append((level, data, logger))


def test_logger_uses_request_context_and_restores_default():
    base_ctx = Context()
    base_ctx.session_id = "base-session"
    set_default_bound_context(base_ctx)
    logger = get_logger("tests.request_scope", context=base_ctx)
    original_emit = logger._emit_event
    events: list = []
    try:
        logger._emit_event = lambda event: events.append(event)

        ctx_a = base_ctx.bind_request(None)
        ctx_a.upstream_session = object()
        ctx_a.request_session_id = "client-a"
        token_a = set_current_request_context(ctx_a)
        try:
            logger.info("from client A")
        finally:
            reset_current_request_context(token_a)

        assert get_current_request_context() is None
        event_a = events[0]
        assert event_a.upstream_session is ctx_a.upstream_session
        assert event_a.context is not None and event_a.context.session_id == "client-a"
        assert getattr(base_ctx, "upstream_session", None) is None

        ctx_b = base_ctx.bind_request(None)
        ctx_b.upstream_session = object()
        ctx_b.request_session_id = "client-b"
        token_b = set_current_request_context(ctx_b)
        try:
            logger.info("from client B")
        finally:
            reset_current_request_context(token_b)

        event_b = events[1]
        assert event_b.upstream_session is ctx_b.upstream_session
        assert event_b.context is not None and event_b.context.session_id == "client-b"
        assert event_a.upstream_session is not event_b.upstream_session
    finally:
        logger._emit_event = original_emit
        set_default_bound_context(None)


def test_exit_request_context_clears_session_level():
    ctx = Context()
    ctx.request_session_id = "client-exit"
    token = set_current_request_context(ctx)
    try:
        LoggingConfig.set_session_min_level("client-exit", "warning")
        assert LoggingConfig.get_session_min_level("client-exit") == "warning"
    finally:
        app_server._exit_request_context(ctx, token)

    # Session override should persist beyond the request lifecycle.
    assert LoggingConfig.get_session_min_level("client-exit") == "warning"
    LoggingConfig.clear_session_min_level("client-exit")


@pytest.mark.asyncio
async def test_concurrent_requests_capture_distinct_sessions():
    base_ctx = Context()
    base_ctx.session_id = "base-session"
    set_default_bound_context(base_ctx)
    logger = get_logger("tests.request_scope.concurrent", context=base_ctx)
    captured: list = []
    original_emit = logger._emit_event
    try:
        logger._emit_event = lambda event: captured.append(event)

        ctx_a = base_ctx.bind_request(None)
        ctx_a.upstream_session = object()
        ctx_a.request_session_id = "client-a"

        ctx_b = base_ctx.bind_request(None)
        ctx_b.upstream_session = object()
        ctx_b.request_session_id = "client-b"

        async def emit(ctx: Context, message: str) -> None:
            token = set_current_request_context(ctx)
            try:
                logger.info(message)
            finally:
                reset_current_request_context(token)

        await asyncio.gather(
            emit(ctx_a, "from-a"),
            emit(ctx_b, "from-b"),
        )

        assert len(captured) == 2
        by_message = {event.message: event for event in captured}
        assert by_message["from-a"].upstream_session is ctx_a.upstream_session
        assert (
            by_message["from-a"].context is not None
            and by_message["from-a"].context.session_id == "client-a"
        )
        assert by_message["from-b"].upstream_session is ctx_b.upstream_session
        assert (
            by_message["from-b"].context is not None
            and by_message["from-b"].context.session_id == "client-b"
        )
    finally:
        logger._emit_event = original_emit
        set_default_bound_context(None)


@pytest.mark.asyncio
async def test_upstream_listener_respects_session_log_level():
    session = _DummySession()
    listener = MCPUpstreamLoggingListener(
        session_level_getter=lambda sid: "warning" if sid == "client-a" else None
    )

    info_event = Event(
        type="info",
        namespace="mcp.test",
        message="should be filtered",
        context=EventContext(session_id="client-a"),
    )
    info_event.upstream_session = session

    await listener.handle_event(info_event)
    assert session.messages == []

    error_event = Event(
        type="error",
        namespace="mcp.test",
        message="should pass",
        context=EventContext(session_id="client-a"),
    )
    error_event.upstream_session = session

    await listener.handle_event(error_event)
    assert len(session.messages) == 1
    level, data, logger_name = session.messages[0]
    assert level == "error"
    assert data["message"] == "should pass"
    assert logger_name == "mcp.test"


def test_logging_config_session_level_helpers_roundtrip():
    original = LoggingConfig._session_min_levels.copy()
    try:
        LoggingConfig.set_session_min_level("session-x", "WARNING")
        assert LoggingConfig.get_session_min_level("session-x") == "warning"

        LoggingConfig.set_session_min_level("session-x", None)
        assert LoggingConfig.get_session_min_level("session-x") is None
    finally:
        LoggingConfig._session_min_levels = original


@pytest.mark.asyncio
async def test_session_log_level_survives_run_unregistration():
    session_id = "client-run-persist"
    run_id = "run-persist"
    execution_id = "exec-persist"

    try:
        LoggingConfig.set_session_min_level(session_id, "warning")

        await app_server._register_session(
            run_id=run_id,
            execution_id=execution_id,
            session=object(),
            identity=None,
            context=None,
            session_id=session_id,
        )

        assert LoggingConfig.get_session_min_level(session_id) == "warning"

        await app_server._unregister_session(run_id)

        assert LoggingConfig.get_session_min_level(session_id) == "warning", (
            "logging override should persist after workflow run completes"
        )
    finally:
        LoggingConfig.clear_session_min_level(session_id)
