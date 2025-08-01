"""
Pytest fixtures for Adaptive Workflow tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import timedelta
from typing import Optional

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class MockAugmentedLLM(AugmentedLLM):
    """Mock AugmentedLLM for testing"""

    def __init__(
        self, agent: Optional[Agent] = None, context: Optional[Context] = None, **kwargs
    ):
        super().__init__(context=context, **kwargs)
        self.agent = agent
        self.generate_mock = AsyncMock()
        self.generate_str_mock = AsyncMock()
        self.generate_structured_mock = AsyncMock()

    async def generate(self, message, request_params=None):
        return await self.generate_mock(message, request_params)

    async def generate_str(self, message, request_params=None):
        return await self.generate_str_mock(message, request_params)

    async def generate_structured(self, message, response_model, request_params=None):
        return await self.generate_structured_mock(
            message, response_model, request_params
        )


@pytest.fixture
def mock_context():
    """Return a mock context for testing"""
    context = MagicMock(spec=Context)

    # Mock required attributes
    context.server_registry = MagicMock()
    context.executor = MagicMock()

    # Mock the agent initialization task response
    async def mock_init_aggregator(*args, **kwargs):
        from mcp_agent.agents.agent import InitAggregatorResponse

        return InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={},
            server_to_tool_map={},
            namespaced_prompt_map={},
            server_to_prompt_map={},
            namespaced_resource_map={},
            server_to_resource_map={},
        )

    context.executor.execute = AsyncMock(side_effect=mock_init_aggregator)
    context.model_selector = MagicMock()
    context.model_selector.select_model = MagicMock(return_value="test-model")
    context.tracing_enabled = False
    context.servers = {"server1": MagicMock(), "server2": MagicMock()}
    context.token_counter = None  # Most tests don't need token counting

    return context


@pytest.fixture
def mock_llm_factory():
    """Return a mock LLM factory function"""

    def factory(agent):
        return MockAugmentedLLM(agent=agent)

    # Make the factory itself a mock so we can assert on it
    mock_factory = MagicMock(side_effect=factory)
    mock_factory.return_value = MockAugmentedLLM()

    return mock_factory


@pytest.fixture
def mock_workflow(mock_llm_factory, mock_context):
    """Return a mock Adaptive Workflow for testing"""
    workflow = AdaptiveWorkflow(
        llm_factory=mock_llm_factory,
        name="TestWorkflow",
        available_servers=["server1", "server2"],
        time_budget=timedelta(minutes=5),
        cost_budget=2.0,
        max_iterations=10,
        max_subagents=20,
        enable_parallel=True,
        enable_learning=False,
        context=mock_context,
    )

    return workflow
