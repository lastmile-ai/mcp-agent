import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent.core.context import Context
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


@pytest.fixture
def mock_context():
    """
    Returns a mock Context instance for testing.
    """
    mock = MagicMock(spec=Context)
    mock.executor = MagicMock()
    return mock


@pytest.fixture
def mock_agent():
    """
    Returns a mock Agent instance for testing.
    """
    mock = MagicMock(spec=Agent)
    # Make context manager methods work
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_llm():
    """
    Returns a mock AugmentedLLM instance for testing.
    """
    mock = MagicMock(spec=AugmentedLLM)
    mock.generate = AsyncMock()
    mock.generate_str = AsyncMock()
    mock.generate_structured = AsyncMock()
    return mock


@pytest.fixture
def mock_llm_factory(mock_llm):
    """
    Returns a mock LLM factory function for testing.
    """
    return AsyncMock(return_value=mock_llm)
