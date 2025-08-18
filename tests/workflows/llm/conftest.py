import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_context():
    """Common mock context fixture usable by all provider tests"""
    mock_context = MagicMock()
    mock_context.executor = MagicMock()
    mock_context.model_selector = MagicMock()

    mock_context.token_counter = MagicMock()
    mock_context.token_counter.push = AsyncMock()
    mock_context.token_counter.pop = AsyncMock()
    mock_context.token_counter.record_usage = AsyncMock()
    mock_context.token_counter.get_summary = AsyncMock()
    mock_context.token_counter.get_tree = AsyncMock()
    mock_context.token_counter.reset = AsyncMock()

    return mock_context
