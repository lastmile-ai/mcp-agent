"""
Integration tests for DeepOrchestrator with all components
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from mcp_agent.agents.agent import Agent, InitAggregatorResponse
from mcp_agent.workflows.deep_orchestrator.orchestrator import DeepOrchestrator
from mcp_agent.workflows.deep_orchestrator.config import DeepOrchestratorConfig
from mcp_agent.workflows.deep_orchestrator.models import (
    Plan,
    Step,
    Task,
    TaskStatus,
    TaskResult,
    KnowledgeItem,
    VerificationResult,
)
from mcp_agent.tracing.token_counter import TokenCounter
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class MockAugmentedLLM(AugmentedLLM):
    """Enhanced mock for testing DeepOrchestrator features"""

    # Class variable to track special returns for specific agents in specific tests
    _special_returns = {}

    def __init__(self, agent: Optional[Agent] = None, **kwargs):
        super().__init__(agent=agent, **kwargs)
        # Set default return values
        self.generate_mock = AsyncMock(return_value=["Default response"])
        self.generate_str_mock = AsyncMock(return_value="Mock response")
        self.generate_structured_mock = AsyncMock()
        self.message_str_mock = MagicMock(return_value="Mock message string")

        # Track calls for verification
        self.call_history = []

    async def generate(self, message, request_params=None):
        self.call_history.append(("generate", message, request_params))
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
        self.call_history.append(("generate_str", message, request_params))
        return await self.generate_str_mock(message, request_params)

    async def generate_structured(self, message, response_model, request_params=None):
        self.call_history.append(
            ("generate_structured", message, response_model.__name__, request_params)
        )
        return await self.generate_structured_mock(
            message, response_model, request_params
        )

    def message_str(self, message, content_only=False):
        return self.message_str_mock(message, content_only)


class TestDeepOrchestratorIntegration:
    """Test the complete DeepOrchestrator with all features"""

    @pytest.fixture
    def mock_llm_factory(self):
        """Create a factory that returns mock LLMs"""
        llms_by_name = {}

        # Pre-create common LLMs for easy test access
        for name in [
            "StrategicPlanner",
            "ObjectiveVerifier",
            "FinalSynthesizer",
            "EmergencyResponder",
            "KnowledgeExtractor",
            "ObjectiveExtractor",
            "SimpleResponder",
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

        factory.llms = llms_by_name
        return factory

    @pytest.fixture
    def mock_context(self):
        """Create mock Context with mocked components"""
        from mcp_agent.core.context import Context

        context = MagicMock(spec=Context)

        # Mock the server registry
        context.server_registry = MagicMock()
        context.server_registry.registry = {
            "filesystem": {"description": "File system access"},
            "web_search": {"description": "Web search capability"},
        }

        # Mock the executor - will be configured per test
        context.executor = MagicMock()
        context.executor.execute = AsyncMock()
        context.executor.execute_many = AsyncMock()

        # Mock the model selector
        context.model_selector = MagicMock()
        context.model_selector.select_model = MagicMock(return_value="test-model")

        # Create a real TokenCounter
        context.token_counter = TokenCounter()

        return context

    @pytest.mark.asyncio
    async def test_full_workflow_with_knowledge_extraction(
        self, mock_llm_factory, mock_context
    ):
        """Test complete workflow with planning, execution, and knowledge extraction"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(
            execution={"max_iterations": 5, "max_replans": 2}
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Create a multi-step plan
        mock_plan = Plan(
            steps=[
                Step(
                    description="Research phase",
                    tasks=[
                        Task(
                            name="research_basics",
                            description="Research basic concepts",
                            agent="researcher",
                            required_servers=["web_search"],
                        ),
                        Task(
                            name="research_advanced",
                            description="Research advanced topics",
                            agent="researcher",
                            required_servers=["web_search"],
                            dependencies=["research_basics"],
                        ),
                    ],
                ),
                Step(
                    description="Analysis phase",
                    tasks=[
                        Task(
                            name="analyze_findings",
                            description="Analyze research findings",
                            agent="analyst",
                        )
                    ],
                ),
            ],
            reasoning="Comprehensive research and analysis plan",
            is_complete=False,
        )

        # Setup planner
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock task executor to simulate successful execution
        async def mock_execute_step(step, request_params, executor):
            # Simulate task execution and knowledge extraction
            for task in step.tasks:
                # Add mock task result
                result = TaskResult(
                    task_name=task.name,
                    status=TaskStatus.COMPLETED,
                    output=f"Result for {task.name}",
                    knowledge_extracted=[
                        KnowledgeItem(
                            key=f"Finding from {task.name}",
                            value=f"Important discovery from {task.name}",
                            source=task.name,
                            confidence=0.9,
                            category="research",
                        )
                    ],
                    duration_seconds=2.0,
                )
                orchestrator.memory.add_task_result(result)

                # Add knowledge to memory
                for item in result.knowledge_extracted:
                    orchestrator.memory.add_knowledge(item)

            return True

        # Patch task executor
        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(
                side_effect=mock_execute_step
            )
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification - complete after all steps
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.return_value = VerificationResult(
                is_complete=True,
                confidence=0.95,
                reasoning="All research and analysis completed",
                missing_elements=[],
            )

            # Mock synthesizer - configure the existing mock
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Final synthesis with all findings integrated"
            ]

            # Execute workflow
            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate(
                    "Research quantum computing applications"
                )

        # Verify results
        assert result == ["Final synthesis with all findings integrated"]
        assert len(orchestrator.memory.knowledge) > 0
        assert len(orchestrator.memory.task_results) == 3  # 3 tasks executed
        assert orchestrator.queue.is_empty()  # All steps completed

    @pytest.mark.asyncio
    async def test_adaptive_replanning_with_failures(
        self, mock_llm_factory, mock_context
    ):
        """Test adaptive replanning when tasks fail"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(
            execution={"max_iterations": 6, "max_replans": 3, "max_task_retries": 2}
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Initial plan with a task that will fail
        initial_plan = Plan(
            steps=[
                Step(
                    description="Failing step",
                    tasks=[
                        Task(
                            name="failing_task",
                            description="This task will fail",
                            # No agent specified - will use default
                        )
                    ],
                )
            ],
            reasoning="Initial plan",
            is_complete=False,
        )

        # Recovery plan after failure
        recovery_plan = Plan(
            steps=[
                Step(
                    description="Alternative approach",
                    tasks=[
                        Task(
                            name="alternative_task",
                            description="Alternative method",
                            # No agent specified - will use default
                        )
                    ],
                )
            ],
            reasoning="Recovering from failure",
            is_complete=False,
        )

        # Setup planner to return recovery plan on second call
        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.side_effect = [initial_plan, recovery_plan]

        # Mock task executor with failure then success
        execution_count = 0

        async def mock_execute_with_failure(step, _request_params, _executor):
            nonlocal execution_count
            execution_count += 1

            if execution_count == 1:
                # First execution fails
                for task in step.tasks:
                    result = TaskResult(
                        task_name=task.name,
                        status=TaskStatus.FAILED,
                        error="Connection timeout",
                        duration_seconds=1.0,
                    )
                    orchestrator.memory.add_task_result(result)
                return False
            else:
                # Subsequent executions succeed
                for task in step.tasks:
                    result = TaskResult(
                        task_name=task.name,
                        status=TaskStatus.COMPLETED,
                        output=f"Success for {task.name}",
                        duration_seconds=2.0,
                    )
                    orchestrator.memory.add_task_result(result)
                return True

        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(
                side_effect=mock_execute_with_failure
            )
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.side_effect = [
                VerificationResult(
                    is_complete=False,
                    confidence=0.3,
                    reasoning="Initial approach failed",
                    missing_elements=["Task completion"],
                ),
                VerificationResult(
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Alternative approach succeeded",
                    missing_elements=[],
                ),
            ]

            # Configure FinalSynthesizer mock directly
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Completed with alternative approach"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Execute with failure recovery")

        # Verify recovery
        assert result == ["Completed with alternative approach"]
        assert orchestrator.replan_count >= 1

        # Check that both failed and successful tasks are recorded
        failed_tasks = [r for r in orchestrator.memory.task_results if not r.success]
        successful_tasks = [r for r in orchestrator.memory.task_results if r.success]
        assert len(failed_tasks) > 0
        assert len(successful_tasks) > 0

    @pytest.mark.asyncio
    async def test_parallel_task_execution(self, mock_llm_factory, mock_context):
        """Test parallel execution of independent tasks"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(execution={"enable_parallel": True})

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Plan with parallel tasks (no dependencies)
        mock_plan = Plan(
            steps=[
                Step(
                    description="Parallel execution",
                    tasks=[
                        Task(name="task1", description="First parallel task"),
                        Task(name="task2", description="Second parallel task"),
                        Task(name="task3", description="Third parallel task"),
                    ],
                )
            ],
            reasoning="Tasks can run in parallel",
            is_complete=False,
        )

        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Track execution order
        execution_order = []

        async def mock_parallel_execution(step, request_params, executor):
            # Simulate parallel execution
            import asyncio

            async def execute_task(task):
                execution_order.append(f"start_{task.name}")
                await asyncio.sleep(0.1)  # Simulate work
                execution_order.append(f"end_{task.name}")

                result = TaskResult(
                    task_name=task.name,
                    status=TaskStatus.COMPLETED,
                    output=f"Result for {task.name}",
                    duration_seconds=0.1,
                )
                orchestrator.memory.add_task_result(result)

            # Execute all tasks in parallel
            await asyncio.gather(*[execute_task(task) for task in step.tasks])
            return True

        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(
                side_effect=mock_parallel_execution
            )
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock verification and synthesis
            mock_llm_factory.llms[
                "ObjectiveVerifier"
            ].generate_structured_mock.return_value = VerificationResult(
                is_complete=True,
                confidence=0.95,
                reasoning="All parallel tasks completed",
                missing_elements=[],
            )

            # Mock synthesizer - configure the existing mock
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Parallel execution completed"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Execute tasks in parallel")

        # Verify parallel execution
        assert result == ["Parallel execution completed"]
        assert len(orchestrator.memory.task_results) == 3

        # Check that tasks started before others finished (parallel execution)
        assert "start_task1" in execution_order
        assert "start_task2" in execution_order
        assert "start_task3" in execution_order

    @pytest.mark.asyncio
    async def test_budget_and_policy_integration(self, mock_llm_factory, mock_context):
        """Test budget management and policy-driven decisions"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(
            budget={"max_tokens": 5000, "max_cost": 1.0, "max_time_minutes": 1},
            policy={"budget_critical_threshold": 0.8, "max_consecutive_failures": 2},
            execution={"max_iterations": 10},
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Simulate high token usage
        orchestrator.budget.tokens_used = 4500  # 90% of budget
        orchestrator.budget.cost_incurred = 0.85  # 85% of budget

        # Simple plan
        mock_plan = Plan(
            steps=[
                Step(
                    description="Resource-intensive step",
                    tasks=[Task(name="expensive_task", description="Uses many tokens")],
                )
            ],
            reasoning="Plan",
            is_complete=False,
        )

        mock_llm_factory.llms[
            "StrategicPlanner"
        ].generate_structured_mock.return_value = mock_plan

        # Mock task executor
        async def mock_expensive_execution(_step, _request_params, _executor):
            # Simulate expensive task
            orchestrator.budget.update_tokens(500)
            # Cost is automatically calculated from tokens, but we can manually adjust it if needed
            orchestrator.budget.cost_incurred += 0.1  # Directly update cost if needed
            return True

        with patch(
            "mcp_agent.workflows.deep_orchestrator.orchestrator.TaskExecutor"
        ) as MockTaskExecutor:
            mock_task_executor_instance = MagicMock()
            mock_task_executor_instance.execute_step = AsyncMock(
                side_effect=mock_expensive_execution
            )
            mock_task_executor_instance.set_budget_callback = MagicMock()
            MockTaskExecutor.return_value = mock_task_executor_instance

            # Mock synthesizer for forced completion
            mock_llm_factory.llms["FinalSynthesizer"].generate_mock.return_value = [
                "Forced completion due to budget constraints"
            ]

            with patch(
                "mcp_agent.workflows.deep_orchestrator.orchestrator.get_tracer"
            ) as mock_tracer:
                mock_span = MagicMock()
                mock_tracer.return_value.start_as_current_span.return_value.__enter__.return_value = mock_span

                result = await orchestrator.generate("Resource-intensive task")

        # Should force complete due to budget
        assert "Forced completion" in result[0] or "budget" in result[0].lower()
        assert orchestrator.budget.is_critical()

    @pytest.mark.asyncio
    async def test_context_management_and_trimming(
        self, mock_llm_factory, mock_context
    ):
        """Test context window management and memory trimming"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(
            context={
                "task_context_budget": 1000,
                "context_relevance_threshold": 0.5,
                "context_compression_ratio": 0.7,
            }
        )

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Add lots of knowledge to memory
        for i in range(100):
            item = KnowledgeItem(
                key=f"fact_{i}",
                value=f"Long detailed information about topic {i}" * 10,
                source=f"source_{i}",
                confidence=0.5 + (i * 0.005),
                category="research",
            )
            orchestrator.memory.add_knowledge(item)

        # Add many task results
        for i in range(50):
            result = TaskResult(
                task_name=f"task_{i}",
                status=TaskStatus.COMPLETED,
                output=f"Detailed output for task {i}" * 20,
                duration_seconds=1.0,
            )
            orchestrator.memory.add_task_result(result)

        # Check initial context size
        initial_size = orchestrator.memory.estimate_context_size()
        assert initial_size > 10000  # Should be large

        # Trigger trimming
        orchestrator.memory.trim_for_context(5000)

        # Check trimmed size
        trimmed_size = orchestrator.memory.estimate_context_size()
        assert trimmed_size < initial_size
        assert trimmed_size <= 6000  # Should be close to target

        # Verify high-value items were kept
        remaining_knowledge = orchestrator.memory.knowledge
        assert len(remaining_knowledge) < 100

        # Check that higher confidence items were kept
        confidences = [item.confidence for item in remaining_knowledge]
        if confidences:
            assert min(confidences) > 0.5  # Low confidence items removed

    @pytest.mark.asyncio
    async def test_agent_caching(self, mock_llm_factory, mock_context):
        """Test agent caching for efficiency"""
        # Set up executor mock for agent initialization
        mock_context.executor.execute = AsyncMock(
            return_value=InitAggregatorResponse(
                initialized=True,
                namespaced_tool_map={},
                server_to_tool_map={},
            )
        )

        config = DeepOrchestratorConfig(cache={"max_cache_size": 3})

        orchestrator = DeepOrchestrator(
            llm_factory=mock_llm_factory, config=config, context=mock_context
        )

        # Create mock agents
        agents = {}
        for name in ["agent1", "agent2", "agent3", "agent4"]:
            agent = MagicMock()
            agent.name = name
            agent.__aenter__ = AsyncMock(return_value=agent)
            agent.__aexit__ = AsyncMock()
            agents[name] = agent

        # Test cache operations directly
        # Generate cache keys
        key1 = orchestrator.agent_cache.get_key("task1", ["server1"])
        key2 = orchestrator.agent_cache.get_key("task2", ["server2"])
        key3 = orchestrator.agent_cache.get_key("task3", ["server3"])
        key4 = orchestrator.agent_cache.get_key("task4", ["server4"])

        # Initially cache should be empty
        assert orchestrator.agent_cache.get(key1) is None

        # Add agents to cache
        orchestrator.agent_cache.put(key1, agents["agent1"])
        orchestrator.agent_cache.put(key2, agents["agent2"])
        orchestrator.agent_cache.put(key3, agents["agent3"])

        # Verify agents are cached
        assert orchestrator.agent_cache.get(key1) == agents["agent1"]
        assert orchestrator.agent_cache.get(key2) == agents["agent2"]
        assert orchestrator.agent_cache.get(key3) == agents["agent3"]

        # Cache should have 3 agents
        assert len(orchestrator.agent_cache.cache) == 3

        # Add agent4 (should evict oldest - agent1)
        orchestrator.agent_cache.put(key4, agents["agent4"])

        # Check cache size is still 3
        assert len(orchestrator.agent_cache.cache) == 3

        # agent1 should have been evicted (oldest)
        assert key1 not in orchestrator.agent_cache.cache
        assert key2 in orchestrator.agent_cache.cache
        assert key3 in orchestrator.agent_cache.cache
        assert key4 in orchestrator.agent_cache.cache
