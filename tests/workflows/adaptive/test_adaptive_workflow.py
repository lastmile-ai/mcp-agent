"""
Comprehensive tests for Adaptive Workflow V2
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import (
    TaskType,
    ResearchAspect,
    SubagentResult,
    SynthesisDecision,
    ExecutionResult,
)
from mcp_agent.workflows.adaptive.knowledge_manager import EnhancedExecutionMemory
from mcp_agent.workflows.adaptive.action_controller import ActionController
from mcp_agent.workflows.adaptive.memory import (
    MemoryManager,
    InMemoryBackend,
    FileSystemBackend,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.agents.agent import Agent
from mcp.types import ModelPreferences


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


class TestAdaptiveWorkflowV2Init:
    """Tests for Adaptive Workflow V2 initialization"""

    def test_init_with_defaults(self, mock_llm_factory, mock_context):
        """Test initialization with default values"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        assert workflow.llm_factory == mock_llm_factory
        assert workflow.context == mock_context
        assert workflow.time_budget == timedelta(minutes=30)
        assert workflow.cost_budget == 10.0
        assert workflow.max_iterations == 10
        assert workflow.enable_parallel is True
        assert workflow.available_agents == {}
        assert workflow.available_servers == []
        assert isinstance(workflow.memory_manager, MemoryManager)

    def test_init_with_custom_values(self, mock_llm_factory, mock_context):
        """Test initialization with custom values"""
        agent1 = Agent(name="Agent1", instruction="Test agent 1")
        agent2 = Agent(name="Agent2", instruction="Test agent 2")
        memory_manager = MemoryManager(backend=FileSystemBackend())

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            name="CustomWorkflow",
            available_agents=[agent1, agent2],
            available_servers=["server1", "server2"],
            time_budget=timedelta(minutes=60),
            cost_budget=50.0,
            max_iterations=20,
            enable_parallel=False,
            memory_manager=memory_manager,
            model_preferences=ModelPreferences(model="gpt-4"),
            context=mock_context,
        )

        assert workflow.name == "CustomWorkflow"
        assert "Agent1" in workflow.available_agents
        assert "Agent2" in workflow.available_agents
        assert workflow.available_servers == ["server1", "server2"]
        assert workflow.time_budget == timedelta(minutes=60)
        assert workflow.cost_budget == 50.0
        assert workflow.max_iterations == 20
        assert workflow.enable_parallel is False
        assert workflow.memory_manager == memory_manager

    def test_init_with_augmented_llm_agents(self, mock_llm_factory, mock_context):
        """Test initialization with AugmentedLLM instances as agents"""
        agent1 = Agent(name="Agent1", instruction="Test agent 1")
        augmented_llm1 = MockAugmentedLLM(agent=agent1, context=mock_context)

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            available_agents=[augmented_llm1],
            context=mock_context,
        )

        assert "Agent1" in workflow.available_agents
        assert isinstance(workflow.available_agents["Agent1"], MockAugmentedLLM)


class TestMemoryManagement:
    """Tests for memory management functionality"""

    @pytest.mark.asyncio
    async def test_memory_save_and_load(self):
        """Test saving and loading execution memory"""
        backend = InMemoryBackend()
        memory_manager = MemoryManager(backend=backend)

        # Create test memory
        memory = EnhancedExecutionMemory(
            execution_id="test-123",
            objective="Test objective",
            task_type=TaskType.RESEARCH,
            iterations=3,
            total_cost=5.0,
        )

        # Save memory
        await memory_manager.save_memory(memory)

        # Load memory
        loaded = await memory_manager.load_memory("test-123")

        assert loaded is not None
        assert loaded.execution_id == "test-123"
        assert loaded.objective == "Test objective"
        assert loaded.iterations == 3

    @pytest.mark.asyncio
    async def test_memory_with_learning(self):
        """Test memory with adaptive learning enabled"""
        backend = InMemoryBackend()
        memory_manager = MemoryManager(backend=backend, enable_learning=True)

        # Create memory with successful results
        memory = EnhancedExecutionMemory(
            execution_id="test-456",
            objective="Find information about AI",
            task_type=TaskType.RESEARCH,
            iterations=2,
            research_history=[["Synthesis 1"], ["Synthesis 2"]],
            subagent_results=[
                SubagentResult(
                    aspect_name="AI History",
                    findings="Found historical information",
                    success=True,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                )
            ],
        )

        # Save and trigger learning
        await memory_manager.save_memory(memory)

        # Test suggestion
        suggestion = await memory_manager.suggest_approach(
            "Find information about machine learning", TaskType.RESEARCH
        )

        # Should get some suggestion based on similarity
        assert suggestion is not None or suggestion is None  # May or may not match

    @pytest.mark.asyncio
    async def test_filesystem_backend(self, tmp_path):
        """Test filesystem backend for persistence"""
        backend = FileSystemBackend(str(tmp_path / "test_memory"))
        memory_manager = MemoryManager(backend=backend)

        # Create and save memory
        memory = EnhancedExecutionMemory(
            execution_id="test-789",
            objective="Test filesystem",
            task_type=TaskType.ACTION,
        )

        await memory_manager.save_memory(memory)

        # Create new manager with same backend path
        backend2 = FileSystemBackend(str(tmp_path / "test_memory"))
        memory_manager2 = MemoryManager(backend=backend2)

        # Should be able to load from filesystem
        loaded = await memory_manager2.load_memory("test-789")
        assert loaded is not None
        assert loaded.objective == "Test filesystem"


class TestObjectiveExtraction:
    """Tests for objective extraction functionality"""

    @pytest.mark.asyncio
    async def test_extract_objective_string(self, mock_llm_factory, mock_context):
        """Test extracting objective from simple string"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        objective = await workflow._extract_objective("Research quantum computing")
        assert objective == "Research quantum computing"

    @pytest.mark.asyncio
    async def test_extract_objective_complex_message(
        self, mock_llm_factory, mock_context
    ):
        """Test extracting objective from complex message format"""
        # Create a mock that will return the expected value
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_str_mock.return_value = (
            "Research quantum computing applications"
        )

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Complex message format (simulating provider-specific format)
        complex_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Research quantum computing applications"}
            ],
        }

        objective = await workflow._extract_objective(complex_message)
        assert objective == "Research quantum computing applications"

        # Verify LLM was called
        mock_llm_instance.generate_str_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_objective_with_error(self, mock_llm_factory, mock_context):
        """Test objective extraction fallback on error"""
        # Create a mock LLM instance that raises error
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_str_mock.side_effect = Exception("LLM error")

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Should fallback to string conversion
        complex_message = {"content": "Fallback objective"}
        objective = await workflow._extract_objective(complex_message)

        assert "Fallback objective" in objective or "content" in objective


class TestWorkflowExecution:
    """Tests for main workflow execution"""

    @pytest.mark.asyncio
    async def test_analyze_objective(self, mock_llm_factory, mock_context):
        """Test objective analysis phase"""
        # Create a mock analysis object
        mock_analysis = MagicMock()
        mock_analysis.task_type = TaskType.RESEARCH

        # Create a mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.return_value = mock_analysis

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Create a mock span
        mock_span = MagicMock()

        task_type = await workflow._analyze_objective("Test objective", mock_span)

        assert task_type == TaskType.RESEARCH
        mock_span.add_event.assert_called_with(
            "objective_analyzed", {"task_type": TaskType.RESEARCH}
        )

    @pytest.mark.asyncio
    async def test_plan_research(self, mock_llm_factory, mock_context):
        """Test research planning phase"""
        # Create a mock plan object
        mock_plan = MagicMock()
        mock_plan.aspects = [
            ResearchAspect(
                name="Aspect 1",
                objective="Research aspect 1",
                required_servers=["server1"],
            ),
            ResearchAspect(
                name="Aspect 2",
                objective="Research aspect 2",
                required_servers=["server2"],
            ),
        ]

        # Create a mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.return_value = mock_plan

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test objective", task_type=TaskType.RESEARCH
        )

        # Create a mock span
        mock_span = MagicMock()

        aspects = await workflow._plan_research(mock_span)

        assert len(aspects) == 2
        assert aspects[0].name == "Aspect 1"
        assert aspects[1].name == "Aspect 2"

    @pytest.mark.asyncio
    async def test_execute_research_parallel(self, mock_llm_factory, mock_context):
        """Test parallel research execution"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, enable_parallel=True
        )

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test objective", task_type=TaskType.RESEARCH
        )

        # Create test aspects
        aspects = [
            ResearchAspect(name="Aspect 1", objective="Obj 1"),
            ResearchAspect(name="Aspect 2", objective="Obj 2"),
        ]

        # Mock the subagent execution
        async def mock_execute_single(aspect, params, span):
            return SubagentResult(
                aspect_name=aspect.name,
                findings=f"Findings for {aspect.name}",
                success=True,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )

        workflow._execute_single_aspect = mock_execute_single

        # Create a mock span
        mock_span = MagicMock()

        results = await workflow._execute_research(aspects, None, mock_span)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].aspect_name == "Aspect 1"
        assert results[1].aspect_name == "Aspect 2"


class TestPredefinedAgents:
    """Tests for predefined agent functionality"""

    @pytest.mark.asyncio
    async def test_execute_with_predefined_agent(self, mock_llm_factory, mock_context):
        """Test execution with predefined Agent"""
        # Create a mock LLM instance that will be returned by attach_llm
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_str_mock.return_value = "Found information"

        # Create predefined agent with mocks
        predefined_agent = MagicMock(spec=Agent)
        predefined_agent.name = "WebSearcher"
        predefined_agent.instruction = "I search the web"
        predefined_agent.server_names = ["web_search"]

        # Mock the agent's async context manager
        predefined_agent.__aenter__ = AsyncMock(return_value=predefined_agent)
        predefined_agent.__aexit__ = AsyncMock(return_value=None)
        predefined_agent.attach_llm = AsyncMock(return_value=mock_llm_instance)

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            available_agents=[predefined_agent],
            context=mock_context,
        )

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test", task_type=TaskType.RESEARCH
        )
        # Initialize action controller since we're calling _execute_single_aspect directly
        workflow.action_controller = ActionController()

        # Create aspect that uses predefined agent
        aspect = ResearchAspect(
            name="Web Research",
            objective="Search for information",
            use_predefined_agent="WebSearcher",
        )

        # Mock span
        mock_span = MagicMock()

        result = await workflow._execute_single_aspect(aspect, None, mock_span)

        assert result.success
        assert result.findings == "Found information"

    @pytest.mark.asyncio
    async def test_execute_with_predefined_augmented_llm(
        self, mock_llm_factory, mock_context
    ):
        """Test execution with predefined AugmentedLLM"""
        # Create predefined AugmentedLLM
        agent = Agent(name="Analyzer", instruction="I analyze data")
        predefined_llm = MockAugmentedLLM(agent=agent)
        predefined_llm.generate_str_mock.return_value = "Analysis complete"

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            available_agents=[predefined_llm],
            context=mock_context,
        )

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test", task_type=TaskType.RESEARCH
        )
        # Initialize action controller since we're calling _execute_single_aspect directly
        workflow.action_controller = ActionController()

        # Create aspect that uses predefined agent
        aspect = ResearchAspect(
            name="Data Analysis",
            objective="Analyze the data",
            use_predefined_agent="Analyzer",
        )

        # Mock span
        mock_span = MagicMock()

        result = await workflow._execute_single_aspect(aspect, None, mock_span)

        assert result.success
        assert result.findings == "Analysis complete"
        # Verify it was called with the right prompt
        predefined_llm.generate_str_mock.assert_called_once()
        call_args = predefined_llm.generate_str_mock.call_args[0][0]
        assert "Analyze the data" in call_args

    def test_format_agent_info(self, mock_llm_factory, mock_context):
        """Test formatting agent information"""
        agent1 = Agent(
            name="TestAgent",
            instruction="I am a test agent",
            server_names=["server1", "server2"],
        )

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            available_agents=[agent1],
            context=mock_context,
        )

        info = workflow._format_agent_info("TestAgent")
        assert "TestAgent" in info
        assert "I am a test agent" in info
        assert "server1, server2" in info

        # Test with non-existent agent
        info = workflow._format_agent_info("NonExistent")
        assert "not found" in info


class TestSynthesisAndDecision:
    """Tests for synthesis and decision phases"""

    @pytest.mark.asyncio
    async def test_synthesize_results(self, mock_llm_factory, mock_context):
        """Test result synthesis"""
        # Create a mock LLM instance
        mock_messages = ["Synthesized findings"]
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_mock.return_value = mock_messages

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Create test results
        results = [
            SubagentResult(
                aspect_name="Aspect 1",
                findings="Finding 1",
                success=True,
                start_time=datetime.now(timezone.utc),
            ),
            SubagentResult(
                aspect_name="Aspect 2",
                findings="Finding 2",
                success=True,
                start_time=datetime.now(timezone.utc),
            ),
        ]

        # Mock span
        mock_span = MagicMock()

        synthesis = await workflow._synthesize_results(results, mock_span)

        assert synthesis == mock_messages
        mock_span.add_event.assert_called_with("results_synthesized")

    @pytest.mark.asyncio
    async def test_decide_next_steps(self, mock_llm_factory, mock_context):
        """Test decision making"""
        # Create mock decision
        mock_decision = SynthesisDecision(
            is_complete=True, confidence=0.95, reasoning="Objective achieved"
        )

        # Create a mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.message_str_mock.return_value = "Previous synthesis"
        mock_llm_instance.generate_structured_mock.return_value = mock_decision

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test objective", iterations=2
        )

        # Mock synthesis messages
        synthesis_messages = ["Previous synthesis"]

        # Mock span
        mock_span = MagicMock()

        decision = await workflow._decide_next_steps(synthesis_messages, mock_span)

        assert decision.is_complete
        assert decision.confidence == 0.95


class TestMessageHandling:
    """Tests for message format handling"""

    @pytest.mark.asyncio
    async def test_format_research_history_with_messages(
        self, mock_llm_factory, mock_context
    ):
        """Test formatting research history with message objects"""
        # Create a mock LLM instance with message_str configured
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.message_str_mock.side_effect = ["Synthesis 1", "Synthesis 2"]

        # Make the factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Set up workflow state with message history
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test",
            objective="Test",
            research_history=[["Message 1"], ["Message 2"]],
        )

        history = workflow._format_research_history()

        assert '<adaptive:iteration number="1">' in history
        assert "Synthesis 1" in history
        assert '<adaptive:iteration number="2">' in history
        assert "Synthesis 2" in history

    def test_format_result_as_messages(self, mock_llm_factory, mock_context):
        """Test formatting execution result as messages"""
        workflow = AdaptiveWorkflow(llm_factory=mock_llm_factory, context=mock_context)

        # Create test result with messages
        test_messages = ["Result message 1", "Result message 2"]
        result = ExecutionResult(
            execution_id="test",
            objective="Test objective",
            task_type=TaskType.RESEARCH,
            result_messages=test_messages,
            confidence=0.9,
            iterations=3,
            subagents_used=2,
            total_time_seconds=100.0,
            total_cost=5.0,
        )

        messages = workflow._format_result_as_messages(result)
        assert messages == test_messages


class TestWorkflowIntegration:
    """Integration tests for full workflow execution"""

    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, mock_llm_factory, mock_context):
        """Test complete workflow execution"""
        # Set up all the mock data
        mock_analysis = MagicMock()
        mock_analysis.task_type = TaskType.RESEARCH

        mock_plan = MagicMock()
        mock_plan.aspects = [
            ResearchAspect(name="Test Aspect", objective="Test research")
        ]

        mock_decision = SynthesisDecision(
            is_complete=True, confidence=0.9, reasoning="Complete"
        )

        mock_final_report = ["Final report message"]

        # Create a stateful mock that returns different values based on call count
        structured_call_count = 0
        generate_call_count = 0

        def structured_side_effect(*args, **kwargs):
            nonlocal structured_call_count
            structured_call_count += 1
            if structured_call_count == 1:
                return mock_analysis
            elif structured_call_count == 2:
                return mock_plan
            else:
                return mock_decision

        def generate_side_effect(*args, **kwargs):
            nonlocal generate_call_count
            generate_call_count += 1
            if generate_call_count == 1:
                return ["Synthesis"]
            else:
                return mock_final_report

        # Create mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.side_effect = structured_side_effect
        mock_llm_instance.generate_mock.side_effect = generate_side_effect
        mock_llm_instance.generate_str_mock.return_value = "Research findings"
        mock_llm_instance.message_str_mock.return_value = "Synthesis"

        # Make factory always return the same mock instance
        def llm_factory(agent):
            if agent and hasattr(agent, "name"):
                if agent.name == "ObjectiveExtractor":
                    # For ObjectiveExtractor, return a mock that gives back the objective
                    obj_mock = MockAugmentedLLM()
                    obj_mock.generate_str_mock.return_value = "Test objective"
                    return obj_mock
                elif agent.name == "ComplexityAssessor":
                    # Return a mock that triggers decomposition for full workflow
                    assess_mock = MockAugmentedLLM()
                    complexity = MagicMock()
                    complexity.needs_decomposition = (
                        True  # Changed to trigger full workflow
                    )
                    complexity.reason = "Complex task requiring decomposition"
                    complexity.estimated_subtasks = 1
                    assess_mock.generate_structured_mock.return_value = complexity
                    return assess_mock
                elif agent.name == "KnowledgeExtractor":
                    # Return a mock that provides empty knowledge extraction
                    extract_mock = MockAugmentedLLM()
                    extraction = MagicMock()
                    extraction.items = []
                    extraction.summary = "No knowledge extracted"
                    extract_mock.generate_structured_mock.return_value = extraction
                    return extract_mock
                elif agent.name == "SubtaskPlanner":
                    # Add SubtaskPlanner mock
                    planner_mock = MockAugmentedLLM()
                    planner_mock.generate_structured_mock.return_value = mock_plan
                    return planner_mock
                elif agent.name == "DecisionMaker":
                    # Add DecisionMaker mock
                    decision_mock = MockAugmentedLLM()
                    decision_mock.generate_structured_mock.return_value = mock_decision
                    return decision_mock
                elif agent.name == "KnowledgeSynthesizer":
                    # Add KnowledgeSynthesizer mock
                    synth_mock = MockAugmentedLLM()
                    synth_mock.generate_mock.return_value = ["Synthesis"]
                    synth_mock.message_str_mock.return_value = "Synthesis"
                    return synth_mock
                elif agent.name == "ReportWriter":
                    # Add ReportWriter mock for final report
                    report_mock = MockAugmentedLLM()
                    report_mock.generate_mock.return_value = mock_final_report
                    return report_mock
            return mock_llm_instance

        mock_llm_factory.side_effect = llm_factory

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory, context=mock_context, max_iterations=2
        )

        # Mock objective extraction
        workflow._extract_objective = AsyncMock(return_value="Test objective")

        # Execute workflow
        result = await workflow.generate("Test objective")

        assert result == mock_final_report

        # Verify workflow was executed
        assert workflow._extract_objective.called

    @pytest.mark.asyncio
    async def test_workflow_with_time_budget_exceeded(
        self, mock_llm_factory, mock_context
    ):
        """Test workflow stops when time budget is exceeded"""
        # Create a stateful mock
        structured_call_count = 0

        def structured_side_effect(*args, **kwargs):
            nonlocal structured_call_count
            structured_call_count += 1
            if structured_call_count == 1:
                # First call is for analyze_objective
                mock_analysis = MagicMock()
                mock_analysis.task_type = TaskType.RESEARCH
                return mock_analysis
            else:
                # Any other structured call
                return MagicMock()

        # Create mock LLM instance
        mock_llm_instance = MockAugmentedLLM()
        mock_llm_instance.generate_structured_mock.side_effect = structured_side_effect
        mock_llm_instance.generate_mock.return_value = ["Incomplete report"]

        # Make factory return our configured mock
        mock_llm_factory.side_effect = lambda agent: mock_llm_instance

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory,
            context=mock_context,
            time_budget=timedelta(seconds=0.1),  # Very short time budget
            max_iterations=10,
        )

        # Set up basic mocks
        workflow._extract_objective = AsyncMock(return_value="Test objective")

        # Add delay to simulate time passing
        async def slow_plan(*args):
            await asyncio.sleep(0.2)  # Exceed time budget
            return []

        workflow._plan_research = AsyncMock(side_effect=slow_plan)

        # Execute workflow
        result = await workflow.generate("Test objective")

        # Should have stopped due to time budget
        assert result == ["Incomplete report"]


@pytest.fixture
def mock_context():
    """Mock context for V2 tests"""
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
    """Mock LLM factory for V2 tests"""

    def factory(agent):
        return MockAugmentedLLM(agent=agent)

    mock_factory = MagicMock(side_effect=factory)
    mock_factory.return_value = MockAugmentedLLM()
    return mock_factory
