from mcp_agent.core.context import Context
from mcp_agent.core.request_context import (
    reset_current_request_context,
    set_current_request_context,
)


def test_bind_request_creates_isolated_contexts():
    base = Context()
    base.session_id = "base"

    ctx_one = base.bind_request(request_context=None)
    ctx_two = base.bind_request(request_context=None)

    session_one = object()
    session_two = object()

    ctx_one.upstream_session = session_one
    ctx_one.request_session_id = "client-one"

    ctx_two.upstream_session = session_two
    ctx_two.request_session_id = "client-two"

    assert base.upstream_session is None
    assert ctx_one.upstream_session is session_one
    assert ctx_two.upstream_session is session_two
    assert ctx_one.session is session_one
    assert ctx_two.session is session_two
    assert ctx_one.request_session_id == "client-one"
    assert ctx_two.request_session_id == "client-two"


def test_session_property_returns_none_when_cleared():
    ctx = Context()
    session = object()

    ctx.upstream_session = session
    assert ctx.session is session

    ctx.upstream_session = None
    assert ctx.session is None


def test_base_context_delegates_to_request_clone():
    base = Context()
    request_ctx = base.bind_request(request_context=None)
    request_ctx.upstream_session = object()

    token = set_current_request_context(request_ctx)
    try:
        assert base.upstream_session is request_ctx.upstream_session
    finally:
        reset_current_request_context(token)

    # After reset the base context should revert to its own session
    assert base.upstream_session is None
