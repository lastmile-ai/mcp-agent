"""
Fixtures for deep_orchestrator tests
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from mcp_agent.core.context import Context
from mcp_agent.tracing.token_counter import TokenCounter


@pytest.fixture
def mock_context():
    """Create a mock Context for testing"""
    context = MagicMock(spec=Context)

    # Mock the server registry
    context.server_registry = MagicMock()
    context.server_registry.registry = {"test_server": {}}

    # Mock the executor
    context.executor = MagicMock()
    context.executor.execute = AsyncMock()

    # Mock the model selector
    context.model_selector = MagicMock()
    context.model_selector.select_model = MagicMock(return_value="test-model")

    context.token_counter = TokenCounter()

    return context


@pytest.fixture
def mock_llm_factory():
    """Create a mock LLM factory"""
    from test_deep_orchestrator import MockAugmentedLLM

    def factory(agent):
        return MockAugmentedLLM(agent=agent)

    return factory
