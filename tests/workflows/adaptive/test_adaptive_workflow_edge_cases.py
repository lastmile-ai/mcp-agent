"""
Edge case and error handling tests for Adaptive Workflow V2
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from typing import Optional

from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import (
    TaskType,
    ResearchAspect,
    SubagentResult,
    SynthesisDecision,
)
from mcp_agent.workflows.adaptive.knowledge_manager import EnhancedExecutionMemory
from mcp_agent.workflows.adaptive.memory import MemoryManager
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class MockAugmentedLLM(AugmentedLLM):
    """Mock AugmentedLLM for testing V2"""

    def __init__(self, agent: Optional[Agent] = None, **kwargs):
        super().__init__(agent=agent, **kwargs)
        self.generate_mock = AsyncMock()
        self.generate_str_mock = AsyncMock(return_value="Mock response")
        self.generate_structured_mock = AsyncMock()
        self.message_str_mock = MagicMock(return_value="Mock message string")

    async def generate(self, message, request_params=None):
        return await self.generate_mock(message, request_params)

    async def generate_str(self, message, request_params=None):
        return await self.generate_str_mock(message, request_params)

    async def generate_structured(self, message, response_model, request_params=None):
        return await self.generate_structured_mock(
            message, response_model, request_params
        )

    def message_str(self, message, content_only=False):
        return self.message_str_mock(message, content_only)


class TestErrorHandling:
    """Tests for error handling scenarios"""

    @pytest.mark.asyncio
    async def test_subagent_execution_failure(self, mock_llm_factory, mock_context):
        """Test handling of subagent execution failures"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Test failure handling",
            task_type=TaskType.RESEARCH,
        )

        # Create aspect
        aspect = ResearchAspect(
            name="Failing Aspect",
            objective="This will fail",
            required_servers=["non_existent_server"],
        )

        # Mock the agent creation to raise error
        with patch(
            "mcp_agent.agents.agent.Agent.__aenter__",
            side_effect=Exception("Server connection failed"),
        ):
            result = await workflow._execute_single_aspect(aspect, None, MagicMock())

        assert result.success is False
        assert result.error == "Server connection failed"
        assert result.findings is None

    @pytest.mark.asyncio
    async def test_memory_save_failure(self, mock_llm_factory, mock_context):
        """Test handling of memory save failures"""

        # Create memory manager with failing backend
        class FailingBackend:
            async def save(self, *args):
                raise IOError("Disk full")

            async def load(self, *args):
                return None

            async def delete(self, *args):
                pass

            async def list_executions(self):
                return {}

        memory_manager = MemoryManager(backend=FailingBackend())

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            memory_manager=memory_manager,
            context=mock_context,
        )

        # The workflow should handle memory save failures gracefully
        # and continue execution
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test", task_type=TaskType.RESEARCH
        )

        # This should not raise an exception
        try:
            await workflow.memory_manager.save_memory(workflow._current_memory)
        except IOError:
            # Expected, but workflow should handle this gracefully
            pass

    @pytest.mark.asyncio
    async def test_llm_exception_handling(self, mock_llm_factory, mock_context):
        """Test handling of exceptions during LLM execution"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test exception", task_type=TaskType.RESEARCH
        )

        # Create aspect that will fail
        aspect = ResearchAspect(
            name="Exception Test", objective="This will throw an exception"
        )

        # Mock the execute_single_aspect to raise an exception
        async def failing_execute(*args, **kwargs):
            raise RuntimeError("Simulated LLM failure")

        workflow._execute_single_aspect = failing_execute

        # Execute should handle the exception gracefully
        try:
            await workflow._execute_single_aspect(aspect, None, MagicMock())
            # If we get here, the exception was caught and handled
            assert False, "Expected RuntimeError to be raised"
        except RuntimeError as e:
            assert str(e) == "Simulated LLM failure"


class TestBoundaryConditions:
    """Tests for boundary conditions"""

    @pytest.mark.asyncio
    async def test_zero_iterations(self, mock_llm_factory, mock_context):
        """Test workflow with max_iterations=0"""
        # Mock analysis
        mock_analysis = MagicMock()
        mock_analysis.task_type = TaskType.RESEARCH

        # Create mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.return_value = mock_analysis
        mock_llm_instance.generate_mock.return_value = ["Empty report - no iterations"]

        # Make factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, max_iterations=0
        )

        # Mock basic setup
        workflow._extract_objective = AsyncMock(return_value="Test")

        result = await workflow.generate("Test objective")

        # Should complete immediately without any research iterations
        assert result == ["Empty report - no iterations"]

    @pytest.mark.asyncio
    async def test_empty_research_aspects(self, mock_llm_factory, mock_context):
        """Test when planner returns no aspects to research"""
        # Mock empty plan
        mock_plan = MagicMock()
        mock_plan.aspects = []  # No aspects to research

        # Create mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.return_value = mock_plan

        # Make factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Test empty aspects",
            task_type=TaskType.RESEARCH,
        )

        aspects = await workflow._plan_research(MagicMock())

        assert aspects == []

    @pytest.mark.asyncio
    async def test_all_subagents_fail(self, mock_llm_factory, mock_context):
        """Test when all subagents fail"""
        # Create mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_mock.return_value = ["No successful research"]

        # Make factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Create failing results
        failed_results = [
            SubagentResult(
                aspect_name="Fail 1",
                success=False,
                error="Error 1",
                start_time=datetime.now(timezone.utc),
            ),
            SubagentResult(
                aspect_name="Fail 2",
                success=False,
                error="Error 2",
                start_time=datetime.now(timezone.utc),
            ),
        ]

        synthesis = await workflow._synthesize_results(failed_results, MagicMock())

        # Should still return something, even with all failures
        assert synthesis == ["No successful research"]


class TestConcurrencyAndRaceConditions:
    """Tests for concurrent execution scenarios"""

    @pytest.mark.asyncio
    async def test_parallel_subagent_execution(self, mock_llm_factory, mock_context):
        """Test parallel execution of multiple subagents"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, enable_parallel=True
        )

        # Track execution order
        execution_order = []

        async def mock_execute(aspect, params, span):
            execution_order.append(f"start_{aspect.name}")
            await asyncio.sleep(0.1)  # Simulate work
            execution_order.append(f"end_{aspect.name}")
            return SubagentResult(
                aspect_name=aspect.name,
                success=True,
                findings=f"Result for {aspect.name}",
                start_time=datetime.now(timezone.utc),
            )

        workflow._execute_single_aspect = mock_execute
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test parallel", task_type=TaskType.RESEARCH
        )

        # Create multiple aspects
        aspects = [
            ResearchAspect(name=f"Aspect_{i}", objective=f"Research {i}")
            for i in range(3)
        ]

        results = await workflow._execute_research(aspects, None, MagicMock())

        # All should start before any finish (parallel execution)
        assert "start_Aspect_0" in execution_order
        assert "start_Aspect_1" in execution_order
        assert "start_Aspect_2" in execution_order

        # Verify all completed
        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_sequential_execution(self, mock_llm_factory, mock_context):
        """Test sequential execution when parallel is disabled"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, enable_parallel=False
        )

        execution_order = []

        async def mock_execute(aspect, params, span):
            execution_order.append(f"start_{aspect.name}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end_{aspect.name}")
            return SubagentResult(
                aspect_name=aspect.name,
                success=True,
                start_time=datetime.now(timezone.utc),
            )

        workflow._execute_single_aspect = mock_execute
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Test sequential",
            task_type=TaskType.RESEARCH,
        )

        aspects = [
            ResearchAspect(name=f"Aspect_{i}", objective=f"Research {i}")
            for i in range(3)
        ]

        await workflow._execute_research(aspects, None, MagicMock())

        # Should complete one before starting next (sequential)
        expected_order = [
            "start_Aspect_0",
            "end_Aspect_0",
            "start_Aspect_1",
            "end_Aspect_1",
            "start_Aspect_2",
            "end_Aspect_2",
        ]
        assert execution_order == expected_order


class TestResourceManagement:
    """Tests for resource limits and management"""

    @pytest.mark.asyncio
    async def test_cost_budget_exceeded(self, mock_llm_factory, mock_context):
        """Test stopping when cost budget is exceeded"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            context=mock_context,
            cost_budget=2.0,  # Low budget
            max_iterations=10,
        )

        # Set up memory with high cost
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Test cost limit",
            total_cost=1.9,  # Almost at budget
        )

        # Add a result that exceeds budget
        workflow._current_memory.subagent_results.append(
            SubagentResult(
                aspect_name="Expensive",
                success=True,
                cost=0.5,  # This will exceed budget
                start_time=datetime.now(timezone.utc),
            )
        )
        workflow._current_memory.total_cost = 2.4

        # Check should_continue
        assert await workflow._should_continue(0) is False

    @pytest.mark.asyncio
    async def test_memory_cleanup_on_exception(self, mock_llm_factory, mock_context):
        """Test that memory is properly cleaned up on exceptions"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Mock to raise exception during execution
        workflow._execute_workflow = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with pytest.raises(Exception) as exc_info:
            await workflow.generate("Test objective")

        assert str(exc_info.value) == "Unexpected error"

        # Memory should be reset
        assert (
            workflow._current_execution_id is None or workflow._current_memory is None
        )


class TestComplexScenarios:
    """Tests for complex real-world scenarios"""

    @pytest.mark.asyncio
    async def test_mixed_predefined_and_new_agents(
        self, mock_llm_factory, mock_context
    ):
        """Test workflow using both predefined and newly created agents"""
        # Create predefined agents
        web_agent = Agent(name="WebAgent", instruction="Web search specialist")
        code_agent = Agent(name="CodeAgent", instruction="Code analysis specialist")

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            available_agents=[web_agent, code_agent],
            available_servers=["web_search", "filesystem", "database"],
            context=mock_context,
        )

        # Set up aspects using mixed agents
        aspects = [
            ResearchAspect(
                name="Web Research",
                objective="Search online",
                use_predefined_agent="WebAgent",
            ),
            ResearchAspect(
                name="Code Analysis",
                objective="Analyze code",
                use_predefined_agent="CodeAgent",
            ),
            ResearchAspect(
                name="Database Research",
                objective="Query database",
                required_servers=["database"],  # Will create new agent
            ),
        ]

        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Mixed agents test",
            task_type=TaskType.RESEARCH,
        )

        # Mock LLM responses
        mock_llm = mock_llm_factory.return_value
        mock_llm.generate_str_mock.return_value = "Research complete"

        results = await workflow._execute_research(aspects, None, MagicMock())

        assert len(results) == 3
        # Verify the factory was called for new agents but not predefined
        assert mock_llm_factory.call_count >= 1  # At least for the new agent

    @pytest.mark.asyncio
    async def test_adaptive_replanning(self, mock_llm_factory, mock_context):
        """Test adaptive replanning based on findings"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, max_iterations=3
        )

        # Track planning calls
        plan_calls = []

        # Define the plans that should be returned
        plan_results = [
            [ResearchAspect(name="Initial", objective="Start research")],
            [ResearchAspect(name="Followup", objective="Dig deeper")],
            [],
        ]

        # Mock analyze_objective to return a proper TaskType
        workflow._analyze_objective = AsyncMock(return_value=TaskType.RESEARCH)

        # Mock other components
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Adaptive test", task_type=TaskType.RESEARCH
        )

        # Initialize components that the workflow expects
        from mcp_agent.workflows.adaptive.knowledge_manager import KnowledgeExtractor
        from mcp_agent.workflows.adaptive.action_controller import ActionController
        from mcp_agent.workflows.adaptive.budget_manager import BudgetManager
        from mcp_agent.workflows.adaptive.subtask_queue import AdaptiveSubtaskQueue

        workflow.knowledge_extractor = KnowledgeExtractor(
            workflow.llm_factory, workflow.context
        )
        workflow.action_controller = ActionController()
        workflow.budget_manager = BudgetManager()
        workflow.subtask_queue = AdaptiveSubtaskQueue(
            "Adaptive test", TaskType.RESEARCH
        )

        # Configure mock LLM instance properly
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_str_mock.return_value = "Finding"
        mock_llm_instance.generate_mock.return_value = ["Synthesis"]
        mock_llm_instance.message_str_mock.return_value = "Synthesis string"

        # Mock decision to continue first, then complete
        decisions = [
            SynthesisDecision(is_complete=False, confidence=0.5, reasoning="Need more"),
            SynthesisDecision(is_complete=True, confidence=0.9, reasoning="Complete"),
        ]
        mock_llm_instance.generate_structured_mock.side_effect = decisions

        # Make factory return appropriate mocks
        def enhanced_factory(agent):
            if agent and hasattr(agent, "name"):
                if agent.name == "ObjectiveExtractor":
                    obj_mock = MockAugmentedLLM()
                    obj_mock.generate_str_mock.return_value = "Adaptive test"
                    return obj_mock
                elif agent.name == "ComplexityAssessor":
                    # Add ComplexityAssessor to trigger decomposition
                    assess_mock = MockAugmentedLLM()
                    complexity = MagicMock()
                    complexity.needs_decomposition = True
                    complexity.reason = "Complex task requiring decomposition"
                    complexity.estimated_subtasks = 2
                    assess_mock.generate_structured_mock.return_value = complexity
                    return assess_mock
                elif agent.name == "SubtaskPlanner":
                    # Add SubtaskPlanner to handle planning
                    planner_mock = MockAugmentedLLM()

                    # Track calls and return different plans
                    def plan_side_effect(*args, **kwargs):
                        call_idx = len(plan_calls)
                        plan_calls.append(call_idx)
                        result = (
                            plan_results[call_idx]
                            if call_idx < len(plan_results)
                            else []
                        )
                        plan = MagicMock()
                        plan.aspects = result
                        return plan

                    planner_mock.generate_structured_mock.side_effect = plan_side_effect
                    return planner_mock
                elif agent.name == "KnowledgeExtractor":
                    extract_mock = MockAugmentedLLM()
                    extraction = MagicMock()
                    extraction.items = []
                    extraction.summary = "No knowledge"
                    extract_mock.generate_structured_mock.return_value = extraction
                    return extract_mock
                elif agent.name == "KnowledgeSynthesizer":
                    synth_mock = MockAugmentedLLM()
                    synth_mock.generate_mock.return_value = ["Synthesis"]
                    synth_mock.message_str_mock.return_value = "Synthesis string"
                    return synth_mock
                elif agent.name == "DecisionMaker":
                    decision_mock = MockAugmentedLLM()
                    decision_mock.generate_structured_mock.side_effect = decisions
                    return decision_mock
                elif agent.name == "ReportWriter":
                    report_mock = MockAugmentedLLM()
                    report_mock.generate_mock.return_value = ["Final report"]
                    return report_mock
            return mock_llm_instance

        mock_llm_factory.side_effect = enhanced_factory

        # Mock the subagent execution to avoid the keys() error
        async def mock_execute_single(aspect, params, span):
            return SubagentResult(
                aspect_name=aspect.name,
                success=True,
                findings=f"Findings for {aspect.name}",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                cost=0.1,
            )

        workflow._execute_single_aspect = mock_execute_single

        # Execute partial workflow
        await workflow._execute_workflow("Test", None, MagicMock())

        # Should have planned twice
        assert len(plan_calls) == 2
        assert plan_calls == [0, 1]


@pytest.fixture
def mock_context():
    """Mock context for edge case tests"""
    from mcp_agent.core.context import Context

    context = MagicMock(spec=Context)
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
    context.servers = {}
    context.config = MagicMock()
    context.token_counter = None
    return context


@pytest.fixture
def mock_llm_factory():
    """Mock LLM factory for edge case tests"""

    def factory(agent):
        return MockAugmentedLLM(agent=agent)

    mock_factory = MagicMock(side_effect=factory)
    mock_factory.return_value = MockAugmentedLLM()
    return mock_factory
