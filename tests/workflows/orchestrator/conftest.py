import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Optional

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.workflows.orchestrator.orchestrator_models import (
    Plan,
    Step,
    StepResult,
    PlanResult,
    TaskWithResult,
    AgentTask,
)


class MockAugmentedLLM(AugmentedLLM):
    """Mock AugmentedLLM for testing the orchestrator"""

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
    """Return a mock context with all required attributes for testing"""
    context = MagicMock(spec=Context)

    # Mock the server registry
    context.server_registry = MagicMock(spec=ServerRegistry)
    context.server_registry.get_server_config.return_value = MagicMock(
        description="Test Server"
    )

    # Mock the executor
    context.executor = MagicMock()
    context.executor.execute = AsyncMock()

    # Mock the model selector
    context.model_selector = MagicMock()
    context.model_selector.select_model = MagicMock(return_value="test-model")

    # Add token_counter attribute
    context.token_counter = None

    return context


@pytest.fixture
def mock_llm_factory():
    """Return a mock LLM factory function"""

    def factory(agent):
        return MockAugmentedLLM(agent=agent)

    return factory


@pytest.fixture
def mock_agents():
    """Return a list of mock agents for testing"""
    return [
        Agent(
            name="test_agent_1",
            instruction="Test agent 1 instruction",
            server_names=["test_server_1"],
        ),
        Agent(
            name="test_agent_2",
            instruction="Test agent 2 instruction",
            server_names=["test_server_2"],
        ),
    ]


@pytest.fixture
def mock_agent_dict(mock_agents):
    """Return a dictionary of mock agents for testing"""
    return {agent.name: agent for agent in mock_agents}


@pytest.fixture
def sample_step():
    """Return a sample Step object for testing"""
    return Step(
        description="Test Step",
        tasks=[
            AgentTask(description="Test Task 1", agent="test_agent_1"),
            AgentTask(description="Test Task 2", agent="test_agent_2"),
        ],
    )


@pytest.fixture
def sample_plan(sample_step):
    """Return a sample Plan object for testing"""
    return Plan(steps=[sample_step], is_complete=False)


@pytest.fixture
def sample_step_result(sample_step):
    """Return a sample StepResult object for testing"""
    return StepResult(
        step=sample_step,
        task_results=[
            TaskWithResult(
                description="Test Task 1", agent="test_agent_1", result="Task 1 result"
            ),
            TaskWithResult(
                description="Test Task 2", agent="test_agent_2", result="Task 2 result"
            ),
        ],
        result="Step completed successfully",
    )


@pytest.fixture
def sample_plan_result(sample_step_result):
    """Return a sample PlanResult object for testing"""
    return PlanResult(
        objective="Test objective",
        plan=Plan(steps=[sample_step_result.step], is_complete=False),
        step_results=[sample_step_result],
        is_complete=False,
        result=None,
    )
