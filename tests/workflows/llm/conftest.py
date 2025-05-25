import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool


@pytest.fixture
def mock_context():
    """Common mock context fixture usable by all provider tests"""
    mock_context = MagicMock()
    mock_context.executor = MagicMock()
    mock_context.model_selector = MagicMock()
    return mock_context


@pytest.fixture
def mock_aggregator():
    """Common mock aggregator fixture"""
    mock_aggregator = MagicMock()
    mock_tools = [
        Tool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
        )
    ]
    mock_aggregator.list_tools = AsyncMock(return_value=MagicMock(tools=mock_tools))
    mock_aggregator.call_tool = AsyncMock()
    return mock_aggregator
