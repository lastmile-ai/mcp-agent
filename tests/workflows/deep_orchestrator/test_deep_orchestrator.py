"""
Comprehensive tests for DeepOrchestrator
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from mcp_agent.agents.agent import Agent, InitAggregatorResponse
from mcp_agent.tracing.token_counter import TokenCounter
from mcp_agent.workflows.deep_orchestrator.orchestrator import DeepOrchestrator
from mcp_agent.workflows.deep_orchestrator.config import DeepOrchestratorConfig
from mcp_agent.workflows.deep_orchestrator.models import (
    Plan,
    Step,
    Task,
    VerificationResult,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class MockAugmentedLLM(AugmentedLLM):
    """Mock AugmentedLLM for testing DeepOrchestrator"""

    # Class variable to track special returns for specific agents in specific tests
    _special_returns = {}

    def __init__(self, agent: Optional[Agent] = None, **kwargs):
        super().__init__(agent=agent, **kwargs)
        # Set default return values
        self.generate_mock = AsyncMock(return_value=["Default response"])
        self.generate_str_mock = AsyncMock(return_value="Mock response")
        self.generate_structured_mock = AsyncMock()
        self.message_str_mock = MagicMock(return_value="Mock message string")

    async def generate(self, message, request_params=None):
        # Check if we have a special return configured for this agent
        if self.agent and hasattr(self.agent, "name"):
            special_return = self._special_returns.get(self.agent.name)
            if special_return:
                return special_return
        return await self.generate_mock(message, request_params)

    @classmethod
    def set_special_return(cls, agent_name, return_value):
        """Set a special return value for a specific agent name"""
        cls._special_returns[agent_name] = return_value

    @classmethod
    def clear_special_returns(cls):
        """Clear all special returns"""
        cls._special_returns.clear()

    async def generate_str(self, message, request_params=None):
        return await self.generate_str_mock(message, request_params)

    async def generate_structured(self, message, response_model, request_params=None):
        return await self.generate_structured_mock(
            message, response_model, request_params
        )

    def message_str(self, message, content_only=False):
        return self.message_str_mock(message, content_only)


class TestDeepOrchestratorInit:
    """Tests for DeepOrchestrator initialization"""

    @pytest.fixture
    def mock_llm_factory(self):
        """Create a mock LLM factory"""

        def factory(agent):
            return MockAugmentedLLM(agent=agent)

        return factory

    @pytest.fixture
    def mock_context(self):
        """Create a mock Context to avoid async initialization issues"""
        from mcp_agent.core.context import Context

        context = MagicMock(spec=Context)

        # Mock the server registry
        context.server_registry = MagicMock()
        context.server_registry.registry = {"server1": {}, "server2": {}}

        # Mock the executor
        context.executor = MagicMock()
        context.executor.execute = AsyncMock()

        # Mock the model selector
        context.model_selector = MagicMock()
        context.model_selector.select_model = MagicMock(return_value="test-model")

        context.token_counter = TokenCounter()

        return context

    def test_init_with_defaults(self, mock_llm_factory, mock_context):
        """Test initialization with default configuration"""
        # Set up executor mock for this specific test
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, context=mock_context
        )

        assert orchestrator.llm_factory == mock_llm_factory
        assert orchestrator.context == mock_context
        assert isinstance(orchestrator.config, DeepOrchestratorConfig)
        assert orchestrator.available_servers == ["server1", "server2"]
        assert orchestrator.agents == {}
        assert orchestrator.memory is not None
        assert orchestrator.queue is not None
        assert orchestrator.budget is not None
        assert orchestrator.policy is not None

    def test_init_with_custom_config(self, mock_llm_factory, mock_context):
        """Test initialization with custom configuration"""
        # Set up executor mock for this specific test
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        agent1 = Agent(name="Agent1", instruction="Test agent 1")
        agent2 = Agent(name="Agent2", instruction="Test agent 2")

        config = DeepOrchestratorConfig(
            name="CustomOrchestrator",
            available_agents=[agent1, agent2],
            available_servers=["custom_server"],
            execution={"max_iterations": 20, "max_replans": 5},
            budget={"max_tokens": 200000, "max_cost": 50.0},
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        assert orchestrator.config.name == "CustomOrchestrator"
        assert "Agent1" in orchestrator.agents
        assert "Agent2" in orchestrator.agents
        assert orchestrator.available_servers == ["custom_server"]
        assert orchestrator.config.execution.max_iterations == 20
        assert orchestrator.config.budget.max_tokens == 200000

    def test_init_without_context(self, mock_llm_factory):
        """Test initialization without context"""
        orchestrator = DeepOrchestrator(llm_factory=mock_llm_factory, context=None)

        # AugmentedLLM creates a context if none provided
        assert orchestrator.context is not None
        assert orchestrator.available_servers == []
        assert orchestrator.memory is not None


class TestDeepOrchestratorExecution:
    """Tests for DeepOrchestrator execution flow"""

    @pytest.fixture(autouse=True)
    def patch_loggers(self):
        """Patch all loggers to avoid initialization issues"""
        with (
            patch("mcp_agent.workflows.deep_orchestrator.orchestrator.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.memory.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.queue.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.policy.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.cache.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.knowledge.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.task_executor.logger"),
            patch("mcp_agent.workflows.deep_orchestrator.context_builder.logger"),
        ):
            yield

    @pytest.fixture
    def mock_llm_factory(self):
        """Create a factory that returns mock LLMs"""
        llms_by_name = {}

        # Pre-create all expected agents with default mocks
        for name in [
            "StrategicPlanner",
            "ObjectiveVerifier",
            "FinalSynthesizer",
            "SimpleResponder",
            "EmergencyResponder",
            "ObjectiveExtractor",
        ]:
            mock_llm = MockAugmentedLLM()
            llms_by_name[name] = mock_llm

        def factory(agent):
            if agent:
                # Always use the same mock instance for the same agent name
                if agent.name not in llms_by_name:
                    llms_by_name[agent.name] = MockAugmentedLLM(agent=agent)
                # Update the agent reference but keep the same mock instance
                mock_llm = llms_by_name[agent.name]
                mock_llm.agent = agent
                return mock_llm
            return MockAugmentedLLM(agent=agent)

        factory.llms = llms_by_name  # Use llms_by_name for test access
        return factory

    @pytest.fixture
    def mock_context(self):
        """Create a mock Context to avoid async initialization issues"""
        from mcp_agent.core.context import Context

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
    def orchestrator(self, mock_llm_factory, mock_context):
        """Create a DeepOrchestrator instance for testing"""
        config = DeepOrchestratorConfig(
            execution={"max_iterations": 5}  # Increased to allow replanning flow
        )
        return DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

    @pytest.mark.asyncio
    async def test_simple_execution_flow(self, orchestrator, mock_llm_factory):
        """Test a simple execution flow with immediate completion"""
        # Set up executor mock for agent initialization
        orchestrator.context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        # Mock the planner to return a complete plan immediately
        mock_plan = Plan(
            steps=[], reasoning="Objective already satisfied", is_complete=True
        )

        # Setup planner mock - configure existing mock
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock simple responder - configure existing mock
        mock_llm_factory.llms["SimpleResponder"].generate_mock.return_value = [
            "Objective already satisfied"
        ]

        # Execute
        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
        ) as mock_tracer:
            mock_span = MagicMock()
            mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

            result = await orchestrator.generate("Test objective")

        assert result == ["Objective already satisfied"]
        assert orchestrator.iteration == 0

    @pytest.mark.asyncio
    async def test_execution_with_steps(self, orchestrator, mock_llm_factory):
        """Test execution with actual steps to process"""
        # Set up executor mock for agent initialization
        orchestrator.context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        # Create a plan with steps
        mock_plan = Plan(
            steps=[
                Step(
                    description="Research phase",
                    tasks=[
                        Task(
                            name="research_task",
                            description="Research the topic",
                            agent="researcher",
                            required_servers=["test_server"],
                        )
                    ],
                )
            ],
            reasoning="Need to research first",
            is_complete=False,
        )

        # Setup planner - configure existing mock
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock TaskExecutor class to track execute_step calls
        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(return_value=True)
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification - configure existing mock
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.return_value = VerificationResult(
                is_complete=True,
                confidence=0.95,
                reasoning="All tasks completed successfully",
                missing_elements=[],
            )

            # Mock synthesizer - configure existing mock
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Final synthesis result"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Research quantum computing")

        assert result == ["Final synthesis result"]
        assert mock_task_executor_instance.execute_step.called

    @pytest.mark.asyncio
    async def test_replanning_flow(self, orchestrator, mock_llm_factory):
        """Test replanning when verification fails"""
        # Set up executor mock for agent initialization
        orchestrator.context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        # Initial plan
        initial_plan = Plan(
            steps=[
                Step(
                    description="Initial step",
                    tasks=[
                        Task(
                            name="task1",
                            description="Do something",
                            # No agent specified - will use default
                        )
                    ],
                )
            ],
            reasoning="Initial plan",
            is_complete=False,
        )

        # Replan with additional steps
        replan = Plan(
            steps=[
                Step(
                    description="Additional step",
                    tasks=[
                        Task(
                            name="task2",
                            description="Do more",
                            # No agent specified - will use default
                        )
                    ],
                )
            ],
            reasoning="Need more work",
            is_complete=False,
        )

        # Setup planner with multiple returns - configure existing mock
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.side_effect = [initial_plan, replan]

        # Mock TaskExecutor class to track execute_step calls
        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(return_value=True)
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification - fail first, then succeed
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.side_effect = [
                VerificationResult(
                    is_complete=False,
                    confidence=0.3,
                    reasoning="Not complete yet",
                    missing_elements=["More research needed"],
                ),
                VerificationResult(
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Now complete",
                    missing_elements=[],
                ),
            ]

            # Configure FinalSynthesizer mock (used after verification succeeds)
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Final result after replanning"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Complex task")

        assert result == ["Final result after replanning"]
        assert orchestrator.replan_count > 0
        assert (
            mock_llm_factory.llms[
                "StrategicPlanner"
            ].generate_structured_mock.call_count
            >= 2
        )

    @pytest.mark.asyncio
    async def test_emergency_completion(self, orchestrator, mock_llm_factory):
        """Test emergency completion when workflow fails"""
        # Set up executor mock for agent initialization
        orchestrator.context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        # Make planner fail - configure existing mock
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.side_effect = Exception("Planner failed")

        # Setup emergency responder - configure existing mock
        mock_llm_factory.llms["EmergencyResponder"].generate_mock.return_value = [
            "Emergency response: partial completion"
        ]

        # Patch Agent class to ensure our factory is used correctly
        with (
            patch("mcp_agent.agents.agent.Agent") as MockAgent,
            patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer,
        ):
            # Configure Agent mock to work with our factory
            def create_agent(*args, **kwargs):
                agent = MagicMock()
                agent.name = kwargs.get("name", "Unknown")
                agent.context = kwargs.get("context")

                async def mock_aenter(self):
                    return self

                async def mock_aexit(self, *args):
                    pass

                async def mock_attach_llm(llm_factory):
                    # Return the pre-configured mock from our factory
                    return llm_factory(agent)

                agent.__aenter__ = lambda: mock_aenter(agent)
                agent.__aexit__ = lambda *args: mock_aexit(agent, *args)
                agent.attach_llm = mock_attach_llm

                return agent

            MockAgent.side_effect = create_agent
            mock_span = MagicMock()
            mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

            result = await orchestrator.generate("Test objective")

        assert result == ["Emergency response: partial completion"]
        assert mock_llm_factory.llms["EmergencyResponder"].generate_mock.called

    @pytest.mark.asyncio
    async def test_execution_with_predefined_agents(
        self, mock_llm_factory, mock_context
    ):
        """Test that tasks can use predefined agents"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        # Create predefined agents
        researcher = Agent(name="researcher", instruction="Research agent")
        analyst = Agent(name="analyst", instruction="Analysis agent")

        config = DeepOrchestratorConfig(
            available_agents=[researcher, analyst], execution={"max_iterations": 5}
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Create a plan that uses the predefined agents
        mock_plan = Plan(
            steps=[
                Step(
                    description="Research and analyze",
                    tasks=[
                        Task(
                            name="research_task",
                            description="Research the topic",
                            agent="researcher",  # Uses predefined agent
                        ),
                        Task(
                            name="analysis_task",
                            description="Analyze findings",
                            agent="analyst",  # Uses predefined agent
                        ),
                    ],
                )
            ],
            reasoning="Using specialized agents",
            is_complete=False,
        )

        # Setup planner
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock TaskExecutor to verify agents are used
        executed_tasks = []

        async def track_execution(step, _request_params, _executor):
            for task in step.tasks:
                executed_tasks.append({"name": task.name, "agent": task.agent})
            return True

        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(
                side_effect=track_execution
            )
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.return_value = VerificationResult(
                is_complete=True,
                confidence=0.95,
                reasoning="Tasks completed",
                missing_elements=[],
            )

            # Mock synthesizer
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Completed with agents"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Test with predefined agents")

        # Verify agents were recognized and used
        assert result == ["Completed with agents"]
        assert len(executed_tasks) == 2
        assert executed_tasks[0]["agent"] == "researcher"
        assert executed_tasks[1]["agent"] == "analyst"

        # Verify the agents are available in orchestrator
        assert "researcher" in orchestrator.agents
        assert "analyst" in orchestrator.agents

    @pytest.mark.asyncio
    async def test_budget_enforcement(self, mock_llm_factory, mock_context):
        """Test that budget limits are enforced"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(
            budget={"max_tokens": 100, "max_cost": 0.01},
            execution={"max_iterations": 10},
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Force budget to be nearly exhausted
        orchestrator.budget.tokens_used = 95
        orchestrator.budget.cost_incurred = 0.009

        # Create a simple plan
        mock_plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                )
            ],
            reasoning="Plan",
            is_complete=False,
        )

        # Configure existing planner mock
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock synthesizer for forced completion - configure existing mock
        mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
            "Forced completion due to budget"
        ]

        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
        ) as mock_tracer:
            mock_span = MagicMock()
            mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

            _result = await orchestrator.generate("Test with budget limit")

        # Should complete early due to budget constraints
        assert orchestrator.iteration <= 2  # Should stop early
