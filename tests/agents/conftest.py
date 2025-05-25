import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool


@pytest.fixture
def mock_context():
    """Common mock context fixture usable by all agent tests"""
    mock_context = MagicMock()
    executor = MagicMock()
    executor.signal = AsyncMock()
    executor.wait_for_signal = AsyncMock(return_value="Test user input")
    mock_context.executor = executor
    mock_context.human_input_handler = None
    mock_context.server_registry = MagicMock()
    return mock_context


@pytest.fixture
def mock_tool():
    """Creates a mock MCP tool for testing"""
    return Tool(
        name="test_tool",
        description="A test tool",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
