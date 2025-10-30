import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from mcp_agent.core.context import Context


@pytest.fixture
def mock_context():
    """Common mock context fixture usable by all provider tests."""
    ctx = MagicMock(spec=Context)

    executor = MagicMock()
    executor.execute = AsyncMock()
    executor.execute_many = AsyncMock()
    ctx.executor = executor

    ctx.model_selector = MagicMock()

    token_counter = MagicMock()
    token_counter.push = AsyncMock()
    token_counter.pop = AsyncMock()
    token_counter.record_usage = AsyncMock()
    token_counter.get_summary = AsyncMock()
    token_counter.get_tree = AsyncMock()
    token_counter.reset = AsyncMock()
    ctx.token_counter = token_counter

    ctx.config = SimpleNamespace(
        openai=None,
        azure=None,
        google=None,
        anthropic=None,
        bedrock=None,
    )

    ctx.request_session_id = None
    ctx.tracing_enabled = False
    ctx.tracing_config = None
    ctx.app = None
    ctx.session_id = None

    return ctx
