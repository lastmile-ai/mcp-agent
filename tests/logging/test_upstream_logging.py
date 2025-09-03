import asyncio
import pytest

from types import SimpleNamespace

from mcp_agent.logging.logger import LoggingConfig, get_logger
from mcp_agent.logging.events import EventFilter
from mcp_agent.logging.transport import AsyncEventBus


class DummyUpstreamSession:
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


@pytest.mark.asyncio
async def test_upstream_logging_listener_sends_notifications(monkeypatch):
    # Ensure clean bus state
    AsyncEventBus.reset()

    dummy_session = DummyUpstreamSession()

    # Configure logging with low threshold so our event passes
    await LoggingConfig.configure(event_filter=EventFilter(min_level="debug"))

    try:
        # Bind a context carrying upstream_session directly to the logger
        ctx_with_upstream = SimpleNamespace(upstream_session=dummy_session)
        logger = get_logger("tests.logging", context=ctx_with_upstream)
        logger.info("hello world", name="unit", foo="bar")

        # Give the async bus a moment to process
        await asyncio.sleep(0.05)

        assert len(dummy_session.calls) >= 1
        call = dummy_session.calls[-1]
        assert call["level"] in ("info", "debug", "warning", "error")
        assert call["logger"].startswith("tests.logging")
        # Ensure our message and custom data are included
        data = call["data"]
        assert data.get("message") == "hello world"
        assert data.get("data", {}).get("foo") == "bar"
    finally:
        await LoggingConfig.shutdown()
        AsyncEventBus.reset()


@pytest.mark.asyncio
async def test_logging_capability_registered_in_fastmcp():
    # Import here to avoid heavy imports at module import time
    from mcp_agent.app import MCPApp
    from mcp_agent.server.app_server import create_mcp_server_for_app
    import mcp.types as types

    app = MCPApp(name="test_app")
    mcp = create_mcp_server_for_app(app)

    low = getattr(mcp, "_mcp_server", None)
    assert low is not None

    # The presence of a SetLevelRequest handler indicates logging capability will be advertised
    assert types.SetLevelRequest in low.request_handlers
