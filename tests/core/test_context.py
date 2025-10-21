import pytest
from types import SimpleNamespace

from mcp_agent.core.context import Context
from mcp_agent.logging.logger import Logger as AgentLogger


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


def test_logger_property_uses_app_logger():
    dummy_logger = _DummyLogger()
    app = SimpleNamespace(mcp=None, logger=dummy_logger, name="demo-app")
    ctx = _make_context(app=app)

    assert ctx.logger is dummy_logger


def test_logger_property_without_app_creates_logger():
    ctx = _make_context()

    logger = ctx.logger

    assert isinstance(logger, AgentLogger)
    assert getattr(logger, "_bound_context", None) is ctx


def test_name_and_description_properties():
    app = SimpleNamespace(
        mcp=None, logger=_DummyLogger(), name="app-name", description="app-desc"
    )
    ctx = _make_context(app=app)
    ctx.config = SimpleNamespace(name="config-name", description="config-desc")

    assert ctx.name == "app-name"
    assert ctx.description == "app-desc"

    ctx_no_app = _make_context()

    assert ctx_no_app.name is None
    assert ctx_no_app.description is None
