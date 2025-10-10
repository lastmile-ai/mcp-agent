import pytest
from types import SimpleNamespace

from mcp_agent.core.context import Context


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def debug(self, message: str):
        self.messages.append(("debug", message))

    def info(self, message: str):
        self.messages.append(("info", message))

    def warning(self, message: str):
        self.messages.append(("warning", message))

    def error(self, message: str):
        self.messages.append(("error", message))


class _DummyMCP:
    def __init__(self):
        self.last_uri = None

    async def read_resource(self, uri):
        self.last_uri = uri
        return [("text", uri)]


def _make_context(*, app: SimpleNamespace | None = None) -> Context:
    ctx = Context()
    if app is not None:
        ctx.app = app
    return ctx


def test_session_prefers_explicit_upstream():
    upstream = object()
    ctx = _make_context()
    ctx.upstream_session = upstream

    assert ctx.session is upstream


def test_fastmcp_fallback_to_app():
    dummy_mcp = object()
    app = SimpleNamespace(mcp=dummy_mcp, logger=None)
    ctx = _make_context(app=app)

    assert ctx.fastmcp is dummy_mcp

    bound = ctx.bind_request(SimpleNamespace(), fastmcp="request_mcp")
    assert bound.fastmcp == "request_mcp"
    # Original context remains unchanged
    assert ctx.fastmcp is dummy_mcp


@pytest.mark.asyncio
async def test_log_falls_back_to_app_logger():
    dummy_logger = _DummyLogger()
    app = SimpleNamespace(mcp=None, logger=dummy_logger)
    ctx = _make_context(app=app)

    await ctx.log("info", "hello world")

    assert ("info", "hello world") in dummy_logger.messages


@pytest.mark.asyncio
async def test_read_resource_falls_back_to_app_mcp():
    dummy_mcp = _DummyMCP()
    app = SimpleNamespace(mcp=dummy_mcp, logger=None)
    ctx = _make_context(app=app)

    contents = await ctx.read_resource("resource://foo")

    assert dummy_mcp.last_uri == "resource://foo"
    assert list(contents) == [("text", "resource://foo")]


@pytest.mark.asyncio
async def test_read_resource_without_mcp_raises():
    ctx = _make_context()

    with pytest.raises(ValueError):
        await ctx.read_resource("resource://missing")
