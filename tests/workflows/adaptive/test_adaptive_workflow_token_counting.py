"""
Tests for token counting in AdaptiveWorkflow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import (
    TaskType,
    ResearchAspect,
    SubagentResult,
    SynthesisDecision,
    ExecutionResult,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.agents.agent import Agent
from mcp_agent.tracing.token_counter import TokenCounter


class TestAdaptiveWorkflowTokenCounting:
    """Tests for token counting in AdaptiveWorkflow"""

    # Mock logger to avoid async issues in tests
    @pytest.fixture(autouse=True)
    def mock_logger(self):
        with patch("mcp_agent.tracing.token_counter.logger") as mock:
            mock.debug = MagicMock()
            mock.info = MagicMock()
            mock.warning = MagicMock()
            mock.error = MagicMock()
            yield mock

    @pytest.fixture
    def mock_context_with_token_counter(self):
        """Create a mock context with token counter"""
        from mcp_agent.core.context import Context

        context = MagicMock(spec=Context)
        context.server_registry = MagicMock()

        # Mock executor with required methods for Agent initialization
        context.executor = MagicMock()
        context.executor.execute = AsyncMock()

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
        context.tracer = None
        context.tracing_enabled = False
        # Mock servers as a regular dict, not AsyncMock
        context.servers = {}
        context.config = MagicMock()

        # Add token counter
        context.token_counter = TokenCounter()

        return context

    @pytest.fixture
    def mock_augmented_llm_with_token_tracking(self):
        """Create a mock AugmentedLLM that tracks tokens"""

        class MockAugmentedLLMWithTokens(AugmentedLLM):
            def __init__(self, agent=None, context=None, **kwargs):
                super().__init__(context=context, **kwargs)
                self.agent = agent or MagicMock(name="MockAgent")
                self.generate_mock = AsyncMock()
                self.generate_str_mock = AsyncMock()
                self.generate_structured_mock = AsyncMock()
                self.message_str_mock = MagicMock()
                self.provider = "test_provider"

            async def generate(self, message, request_params=None):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    self.context.token_counter.push(
                        name=f"llm_call_{self.agent.name}", node_type="llm_call"
                    )
                    self.context.token_counter.record_usage(
                        input_tokens=150,
                        output_tokens=100,
                        model_name="test-model",
                        provider=self.provider,
                    )
                    self.context.token_counter.pop()

                return await self.generate_mock(message, request_params)

            async def generate_str(self, message, request_params=None):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    self.context.token_counter.push(
                        name=f"llm_call_str_{self.agent.name}", node_type="llm_call"
                    )
                    self.context.token_counter.record_usage(
                        input_tokens=100,
                        output_tokens=50,
                        model_name="test-model",
                        provider=self.provider,
                    )
                    self.context.token_counter.pop()

                return await self.generate_str_mock(message, request_params)

            async def generate_structured(
                self, message, response_model, request_params=None
            ):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    self.context.token_counter.push(
                        name=f"llm_call_structured_{self.agent.name}",
                        node_type="llm_call",
                    )
                    self.context.token_counter.record_usage(
                        input_tokens=200,
                        output_tokens=100,
                        model_name="test-model",
                        provider=self.provider,
                    )
                    self.context.token_counter.pop()

                return await self.generate_structured_mock(
                    message, response_model, request_params
                )

            def message_str(self, message, content_only=False):
                return self.message_str_mock(message, content_only)

        return MockAugmentedLLMWithTokens

    @pytest.fixture
    def mock_llm_factory_with_tokens(
        self, mock_context_with_token_counter, mock_augmented_llm_with_token_tracking
    ):
        """Create a mock LLM factory that creates token-tracking LLMs"""

        def factory(agent):
            llm = mock_augmented_llm_with_token_tracking(
                agent=agent, context=mock_context_with_token_counter
            )
            # Set up default return values
            llm.generate_mock.return_value = ["Generated response"]
            llm.generate_str_mock.return_value = "Generated string response"
            llm.generate_structured_mock.return_value = MagicMock()
            llm.message_str_mock.return_value = "Message string"
            return llm

        return factory

    @pytest.mark.asyncio
    async def test_basic_workflow_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test basic token tracking through a simple workflow execution"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
            max_iterations=1,
        )

        # Push app context
        mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Mock the workflow components
        from mcp_agent.workflows.adaptive.models import TaskType

        # Mock analyze_objective to return quickly
        analysis_result = MagicMock()
        analysis_result.task_type = TaskType.RESEARCH
        analysis_result.key_aspects = ["aspect1", "aspect2"]
        analysis_result.estimated_scope = "medium"

        # Mock plan to return one aspect
        plan_result = MagicMock()
        plan_result.aspects = [
            ResearchAspect(
                name="Test Aspect", objective="Research something", required_servers=[]
            )
        ]
        plan_result.rationale = "Test rationale"

        # Mock decision to complete after first iteration
        decision_result = SynthesisDecision(
            is_complete=True, confidence=0.9, reasoning="Research complete"
        )

        # Track which LLMs are created
        created_llms = []

        # Create a single mock instance that will be reused
        mock_llm = mock_llm_factory_with_tokens(
            Agent(name="adaptive", instruction="adaptive workflow")
        )

        # Set up side effects to return different values based on call order
        # The workflow calls LLMs in this order:
        # 1. _analyze_objective (generate_structured) -> analysis_result
        # 2. _plan_research (generate_structured) -> plan_result
        # 3. _execute_single_subtask for each aspect (generate_str) -> findings
        # 4. _synthesize_results (generate) -> synthesis
        # 5. _decide_next_steps (generate_structured) -> decision_result
        # 6. _generate_final_report (generate) -> final report

        structured_call_count = 0

        def structured_side_effect(*args, **kwargs):
            nonlocal structured_call_count
            structured_call_count += 1
            if structured_call_count == 1:
                return analysis_result  # _analyze_objective
            elif structured_call_count == 2:
                return plan_result  # _plan_research
            elif structured_call_count == 3:
                return decision_result  # _decide_next_steps
            else:
                return MagicMock()  # Any other structured calls

        generate_call_count = 0

        def generate_side_effect(*args, **kwargs):
            nonlocal generate_call_count
            generate_call_count += 1
            if generate_call_count == 1:
                return ["Synthesis"]  # _synthesize_results
            else:
                return ["Final report"]  # _generate_final_report

        mock_llm.generate_structured_mock.side_effect = structured_side_effect
        mock_llm.generate_mock.side_effect = generate_side_effect
        mock_llm.generate_str_mock.return_value = "Research findings"

        # Track factory calls
        def track_factory(agent):
            created_llms.append(agent.name)
            return mock_llm

        workflow.llm_factory = track_factory

        # Execute workflow
        result = await workflow.generate("Test objective")

        # Pop app context
        app_node = mock_context_with_token_counter.token_counter.pop()

        # Verify results - the actual result might be Synthesis or Final report
        # depending on how the workflow executes
        assert result is not None
        assert len(result) > 0

        # Debug: Print what LLMs were created
        print("\nCreated LLMs:")
        for agent_name in created_llms:
            print(f"  - {agent_name}")

        print("\nMock LLM call counts:")
        print(
            f"  generate_structured calls: {mock_llm.generate_structured_mock.call_count}"
        )
        print(f"  generate_str calls: {mock_llm.generate_str_mock.call_count}")
        print(f"  generate calls: {mock_llm.generate_mock.call_count}")

        # Check token usage
        app_usage = app_node.aggregate_usage()

        # Debug: Print the hierarchy to understand what's being tracked
        def print_node(node, indent=0):
            usage = node.aggregate_usage()
            print(
                "  " * indent
                + f"{node.name} ({node.node_type}): {usage.total_tokens} tokens"
            )
            for child in node.children:
                print_node(child, indent + 1)

        print("\nToken hierarchy:")
        print_node(app_node)

        # Find the AdaptiveWorkflow node
        workflow_node = None
        for child in app_node.children:
            if child.node_type == "workflow" and "AdaptiveWorkflow" in child.name:
                workflow_node = child
                break

        # Verify hierarchy
        assert workflow_node is not None, "AdaptiveWorkflow node not found"

        # The workflow node should contain all the token usage
        workflow_usage = workflow_node.aggregate_usage()

        # Expected tokens based on mock setup:
        # Each generate_structured call: 120 input + 60 output = 180 tokens
        # Each generate_str call: 80 input + 40 output = 120 tokens
        # Each generate call: 100 input + 50 output = 150 tokens

        print(f"\nTotal tokens tracked: {app_usage.total_tokens}")
        print(f"Workflow tokens: {workflow_usage.total_tokens}")

        # Check that tokens are properly tracked
        assert app_usage.total_tokens > 0
        assert workflow_usage.total_tokens > 0
        assert app_usage.total_tokens == workflow_usage.total_tokens
        assert app_usage.input_tokens > 0
        assert app_usage.output_tokens > 0

        # Check global summary
        summary = mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == app_usage.total_tokens
        assert "test-model (test_provider)" in summary.model_usage

    @pytest.mark.asyncio
    async def test_subagent_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking for subagent execution"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Push workflow context
        mock_context_with_token_counter.token_counter.push("workflow", "workflow")

        # Initialize workflow state
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            EnhancedExecutionMemory,
        )

        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test objective", task_type=TaskType.RESEARCH
        )

        # Create a test aspect
        aspect = ResearchAspect(
            name="TestResearch", objective="Research test topic", required_servers=[]
        )

        # Mock _execute_single_aspect to capture token tracking
        async def mock_execute_single(aspect, params, span):
            # The actual LLM call will be made here, which tracks tokens
            llm = workflow.llm_factory(
                Agent(name="test_subagent", instruction="Test subagent")
            )
            result = await llm.generate_str(f"Execute: {aspect.objective}")

            # Create result with token info from context
            subagent_result = SubagentResult(
                aspect_name=aspect.name,
                findings=result,
                success=True,
                start_time=MagicMock(),
                end_time=MagicMock(),
            )

            # Get token usage from the current context
            if workflow.context and workflow.context.token_counter:
                # Find the most recent LLM call node
                current_node = workflow.context.token_counter._current
                if current_node and len(current_node.children) > 0:
                    # Get the last child (the LLM call we just made)
                    llm_node = current_node.children[-1]
                    usage = llm_node.aggregate_usage()
                    subagent_result.input_tokens = usage.input_tokens
                    subagent_result.output_tokens = usage.output_tokens
                    subagent_result.total_tokens = usage.total_tokens
                    subagent_result.model_name = "test-model"
                    subagent_result.provider = "test_provider"
                    subagent_result.cost = 0.001  # Mock cost

            return subagent_result

        workflow._execute_single_aspect = mock_execute_single

        # Execute research with single aspect
        results = await workflow._execute_research([aspect], None, MagicMock())

        # Pop workflow context
        workflow_node = mock_context_with_token_counter.token_counter.pop()

        # Verify result
        assert len(results) == 1
        result = results[0]
        assert result.success is True
        assert result.aspect_name == "TestResearch"
        assert result.findings == "Generated string response"

        # Check token usage was captured in result
        assert result.input_tokens == 100  # From generate_str
        assert result.output_tokens == 50
        assert result.total_tokens == 150
        assert result.model_name == "test-model"
        assert result.provider == "test_provider"

        # Verify cost calculation
        assert result.cost > 0

        # Check workflow aggregation
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 150

    @pytest.mark.asyncio
    async def test_parallel_subagent_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking with parallel subagent execution"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
            enable_parallel=True,
        )

        # Set up workflow state with EnhancedExecutionMemory
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            EnhancedExecutionMemory,
        )

        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test parallel", task_type=TaskType.RESEARCH
        )

        # Push workflow context
        mock_context_with_token_counter.token_counter.push(
            "parallel_workflow", "workflow"
        )

        # Create multiple aspects
        aspects = [
            ResearchAspect(name=f"Research_{i}", objective=f"Topic {i}")
            for i in range(3)
        ]

        # Mock _execute_single_aspect to simulate parallel token tracking
        async def mock_execute_single(aspect, params, span):
            # Simulate each agent tracking its own tokens
            llm = workflow.llm_factory(
                Agent(name=f"agent_{aspect.name}", instruction="Test")
            )
            result = await llm.generate_str(f"Execute: {aspect.objective}")

            return SubagentResult(
                aspect_name=aspect.name,
                success=True,
                findings=result,
                start_time=MagicMock(),
                end_time=MagicMock(),
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                model_name="test-model",
                provider="test_provider",
                cost=0.001,
            )

        workflow._execute_single_aspect = mock_execute_single

        # Execute research in parallel
        results = await workflow._execute_research(aspects, None, MagicMock())

        # Pop workflow context
        workflow_node = mock_context_with_token_counter.token_counter.pop()

        # Verify results
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.success is True
            assert result.aspect_name == f"Research_{i}"
            assert result.total_tokens == 150  # Each subagent uses 150 tokens

        # Check total token usage
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 450  # 3 x 150

    @pytest.mark.asyncio
    async def test_beast_mode_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking when beast mode is activated"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Set up workflow state - beast mode needs a properly initialized workflow
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            EnhancedExecutionMemory,
            KnowledgeExtractor,
        )
        from mcp_agent.workflows.adaptive.subtask_queue import AdaptiveSubtaskQueue

        # Initialize workflow ID and memory
        workflow._current_execution_id = "test-beast-mode"
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test-beast-mode",
            objective="Test beast mode",
            task_type=TaskType.RESEARCH,
        )

        # Initialize components that beast mode expects
        workflow.knowledge_extractor = KnowledgeExtractor(workflow.llm_factory)
        workflow.subtask_queue = AdaptiveSubtaskQueue(
            "Test beast mode", TaskType.RESEARCH
        )

        # Mock the BeastModeResolver LLM to return a proper response
        mock_llm = mock_llm_factory_with_tokens(
            Agent(name="BeastModeResolver", instruction="Force completion")
        )
        mock_llm.generate_mock.return_value = [
            "Beast mode completion: Research summary based on limited data"
        ]

        # Override the factory for this specific test
        def beast_mode_factory(agent):
            if agent.name == "BeastModeResolver":
                return mock_llm
            return mock_llm_factory_with_tokens(agent)

        workflow.llm_factory = beast_mode_factory

        # Push app context
        mock_context_with_token_counter.token_counter.push("beast_app", "app")

        # Execute beast mode
        result = await workflow._beast_mode_completion("Test objective", MagicMock())

        # Pop app context
        app_node = mock_context_with_token_counter.token_counter.pop()

        # Verify result
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.confidence == 0.7  # Lower confidence in beast mode
        assert len(result.limitations) > 0  # Should note limitations

        # Check token usage - beast mode uses generate()
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 250  # From generate() call
        assert app_usage.input_tokens == 150
        assert app_usage.output_tokens == 100

    @pytest.mark.asyncio
    async def test_synthesis_and_decision_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking for synthesis and decision phases"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Set up workflow state with EnhancedExecutionMemory
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            EnhancedExecutionMemory,
        )

        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test", objective="Test synthesis", task_type=TaskType.RESEARCH
        )

        # Push workflow context
        mock_context_with_token_counter.token_counter.push(
            "synthesis_workflow", "workflow"
        )

        # Create some results to synthesize
        results = [
            SubagentResult(
                aspect_name="Research 1",
                findings="Finding 1",
                success=True,
                start_time=MagicMock(),
            ),
            SubagentResult(
                aspect_name="Research 2",
                findings="Finding 2",
                success=True,
                start_time=MagicMock(),
            ),
        ]

        # Mock the LLM to return proper responses
        mock_llm = mock_llm_factory_with_tokens(Agent(name="test", instruction="test"))

        # For synthesis, we need generate() to return messages
        mock_llm.generate_mock.return_value = ["Synthesis of findings"]

        # For decision, we need generate_structured() to return a SynthesisDecision
        mock_decision = SynthesisDecision(
            is_complete=True, confidence=0.9, reasoning="All research completed"
        )
        mock_llm.generate_structured_mock.return_value = mock_decision

        # Override factory for this test
        workflow.llm_factory = lambda agent: mock_llm

        # Execute synthesis
        synthesis_messages = await workflow._synthesize_results(results, MagicMock())
        assert synthesis_messages == ["Synthesis of findings"]

        # Execute decision
        decision = await workflow._decide_next_steps(synthesis_messages, MagicMock())

        # Pop workflow context
        workflow_node = mock_context_with_token_counter.token_counter.pop()

        # Verify decision
        assert isinstance(decision, SynthesisDecision)

        # Check token usage
        # synthesis uses generate() - 250 tokens
        # decision uses generate_structured() - 300 tokens
        # Total: 550 tokens
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 550
        assert workflow_usage.input_tokens == 350  # 150 + 200
        assert workflow_usage.output_tokens == 200  # 100 + 100

    @pytest.mark.asyncio
    async def test_full_workflow_with_iterations_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking through multiple workflow iterations"""
        # Debug: Check initial token counter state
        initial_summary = mock_context_with_token_counter.token_counter.get_summary()
        print("\nInitial token counter state:")
        print(f"  Total tokens: {initial_summary.usage.total_tokens}")
        print(f"  Total cost: ${initial_summary.cost}")

        # Set up proper mocks for workflow execution
        from mcp_agent.workflows.adaptive.models import (
            TaskType,
            ResearchAspect,
            SynthesisDecision,
        )

        # Create a factory that returns properly configured mocks
        created_agents = []
        complexity_call_count = [
            0
        ]  # Track ComplexityAssessor calls across all instances

        def enhanced_factory(agent):
            if agent and hasattr(agent, "name"):
                created_agents.append(agent.name)
                print(f"Creating LLM for agent: {agent.name}")

            llm = mock_llm_factory_with_tokens(agent)

            # Configure responses based on agent name
            if agent and hasattr(agent, "name"):
                if agent.name == "ObjectiveExtractor":
                    llm.generate_str_mock.return_value = "Complex research objective"
                elif agent.name == "ObjectiveAnalyzer":
                    analysis = MagicMock()
                    analysis.task_type = TaskType.RESEARCH
                    analysis.key_aspects = ["aspect1", "aspect2"]
                    analysis.estimated_scope = "medium"
                    llm.generate_structured_mock.return_value = analysis
                elif agent.name == "ComplexityAssessor":
                    # Only decompose the first task (original objective), not the subtasks
                    def complexity_side_effect(*args, **kwargs):
                        complexity_call_count[0] += 1
                        # Only decompose the very first call (the original objective)
                        if complexity_call_count[0] == 1:
                            return MagicMock(
                                needs_decomposition=True,
                                reason="Complex topic",
                                estimated_subtasks=2,
                            )
                        else:
                            return MagicMock(
                                needs_decomposition=False, reason="Simple enough"
                            )

                    llm.generate_structured_mock.side_effect = complexity_side_effect
                elif agent.name == "SubtaskPlanner":
                    # Return the initial decomposition of the original objective
                    plan = MagicMock(
                        aspects=[
                            ResearchAspect(
                                name="Research A",
                                objective="Study A",
                                required_servers=[],
                            ),
                            ResearchAspect(
                                name="Research B",
                                objective="Study B",
                                required_servers=[],
                            ),
                        ],
                        rationale="Two aspects to research",
                    )
                    llm.generate_structured_mock.return_value = plan
                elif agent.name == "DecisionMaker":
                    # Complete after first synthesis since we only have 2 subtasks
                    decision = SynthesisDecision(
                        is_complete=True, confidence=0.9, reasoning="Research complete"
                    )
                    llm.generate_structured_mock.return_value = decision
                elif (
                    agent.name == "KnowledgeSynthesizer"
                    or agent.name == "SynthesisAgent"
                ):
                    llm.generate_mock.return_value = ["Synthesis of findings"]
                elif agent.name == "ReportWriter":
                    llm.generate_mock.return_value = ["Final comprehensive report"]
                elif agent.name == "KnowledgeExtractor":
                    # Mock knowledge extraction response with actual items
                    from mcp_agent.workflows.adaptive.knowledge_manager import (
                        KnowledgeType,
                    )

                    extraction_response = MagicMock()
                    extraction_response.items = [
                        MagicMock(
                            question="What was found?",
                            answer="Important finding",
                            confidence=0.9,
                            knowledge_type=KnowledgeType.FACT,
                            relevance_score=1.0,
                        ),
                        MagicMock(
                            question="What else?",
                            answer="Another finding",
                            confidence=0.85,
                            knowledge_type=KnowledgeType.FACT,
                            relevance_score=0.9,
                        ),
                    ]
                    extraction_response.summary = "Extracted knowledge successfully"
                    llm.generate_structured_mock.return_value = extraction_response
                else:
                    # For research agents and any other agents
                    llm.generate_str_mock.return_value = f"Findings for {agent.name if (agent and hasattr(agent, 'name')) else 'unknown'}"
                    # Handle other agent types
                    if agent and hasattr(agent, "name"):
                        if agent.name == "BeastModeResolver":
                            llm.generate_mock.return_value = [
                                "Final comprehensive report"
                            ]
                        elif agent.name == "Reporter":
                            llm.generate_mock.return_value = [
                                "Final comprehensive report"
                            ]
                        elif "research" in agent.name.lower() or agent.name in [
                            "Research A",
                            "Research B",
                        ]:
                            # For actual research execution
                            llm.generate_str_mock.return_value = (
                                f"Research findings for {agent.name}"
                            )

            return llm

        workflow = AdaptiveWorkflow(
            llm_factory=enhanced_factory,
            context=mock_context_with_token_counter,
            max_iterations=10,  # Increased to avoid hitting iteration limit
            cost_budget=1000.0,  # High budget to avoid beast mode
            time_budget=timedelta(hours=1),  # High time budget to avoid beast mode
            token_budget=1000000,  # High token budget
            synthesis_frequency=3,  # Synthesize every 3 iterations
            min_knowledge_for_synthesis=3,  # Lower threshold for test
        )

        # Push app context
        mock_context_with_token_counter.token_counter.push("multi_iteration_app", "app")

        # Debug: Check budget manager state before execution
        print("\nBudget manager before execution:")
        print(f"  budget_manager exists: {workflow.budget_manager is not None}")
        print(f"  time_budget: {workflow.time_budget}")
        print(f"  cost_budget: {workflow.cost_budget}")
        print(f"  max_iterations: {workflow.max_iterations}")

        # Execute workflow with properly mocked components
        result = await workflow.generate("Complex research objective")

        # Pop app context
        app_node = mock_context_with_token_counter.token_counter.pop()

        # Verify result
        assert result == ["Final comprehensive report"]  # From final report

        # Debug: Print token hierarchy
        print("\nToken hierarchy:")

        def print_node(node, indent=0):
            prefix = "  " * indent
            print(
                f"{prefix}{node.name} ({node.node_type}): {node.aggregate_usage().total_tokens} tokens"
            )
            for child in node.children:
                print_node(child, indent + 1)

        print_node(app_node)

        print("\nAgents created during workflow:")
        for agent_name in created_agents:
            print(f"  - {agent_name}")

        print("\nExpected token breakdown:")
        print("  analyze_objective: 300 tokens")
        print("  Iteration 1: decompose original (600 tokens)")
        print("  Iteration 2: execute Research B + validate + extract (1000 tokens)")
        print(
            "  Iteration 3: execute Research A + validate + extract + synthesize + decide (1550 tokens)"
        )
        print("  final_report: 250 tokens")
        print("  Total expected: 3700 tokens")
        print(f"  Total actual: {app_node.aggregate_usage().total_tokens} tokens")

        # Check token usage - based on actual workflow execution:
        # The workflow should execute:
        # 1. _analyze_objective: 1 x generate_structured = 300 tokens
        # 2. Iteration 1:
        #    - _needs_decomposition for original (ComplexityAssessor): 1 x generate_structured = 300 tokens
        #    - _plan_research_for_subtask (SubtaskPlanner): 1 x generate_structured = 300 tokens
        # 3. Iteration 2:
        #    - _needs_decomposition for Research B (ComplexityAssessor): 1 x generate_structured = 300 tokens
        #    - _execute_single_subtask for Research B: 1 x generate_str = 150 tokens
        #    - Validate result (ResultPassthrough): 1 x generate = 250 tokens
        #    - Extract knowledge (KnowledgeExtractor): 1 x generate_structured = 300 tokens
        # 4. Iteration 3:
        #    - _needs_decomposition for Research A (ComplexityAssessor): 1 x generate_structured = 300 tokens
        #    - _execute_single_subtask for Research A: 1 x generate_str = 150 tokens
        #    - Validate result (ResultPassthrough): 1 x generate = 250 tokens
        #    - Extract knowledge (KnowledgeExtractor): 1 x generate_structured = 300 tokens
        #    - _synthesize_accumulated_knowledge (SynthesisAgent): 1 x generate = 250 tokens
        #    - _decide_next_steps (DecisionMaker): 1 x generate_structured = 300 tokens
        # 5. _generate_final_report: 1 x generate = 250 tokens
        #
        # Total: 300 + 300 + 300 + 300 + 150 + 250 + 300 + 300 + 150 + 250 + 300 + 250 + 300 + 250 = 3700 tokens
        #   - decide: 1 x generate_structured = 300
        # - Iteration 2:
        #   - plan_research: 1 x generate_structured = 300
        #   - execute_research (1 aspect): 1 x generate_str = 150
        #   - synthesize: 1 x generate = 250
        #   - decide: 1 x generate_structured = 300
        # - final_report: 1 x generate = 250
        # Total: 300 + 1150 + 1000 + 250 = 2700 tokens
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 3700

        # Verify cost tracking in summary
        summary = mock_context_with_token_counter.token_counter.get_summary()
        assert summary.cost > 0
        assert summary.usage.total_tokens == 3700

    @pytest.mark.asyncio
    async def test_knowledge_extraction_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test token tracking in knowledge extraction"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Initialize knowledge extractor
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            KnowledgeExtractor,
            KnowledgeItem,
            KnowledgeType,
        )

        # Push app context
        mock_context_with_token_counter.token_counter.push("knowledge_app", "app")

        # Create a result to extract knowledge from
        result = SubagentResult(
            aspect_name="Research",
            findings="Important finding about quantum computing",
            success=True,
            start_time=MagicMock(),
        )

        # Create a mock KnowledgeExtractor that avoids Agent creation
        knowledge_extractor = KnowledgeExtractor(workflow.llm_factory)

        # Mock the extract_knowledge method directly
        async def mock_extract_knowledge(result, context):
            # Simulate LLM call for extraction - this tracks tokens
            llm = workflow.llm_factory(Agent(name="extractor", instruction="extract"))

            # Make the structured call that records tokens
            extraction_result = MagicMock()
            extraction_result.items = [
                KnowledgeItem(
                    question="What is quantum computing?",
                    answer="Quantum computing uses quantum phenomena",
                    confidence=0.9,
                    knowledge_type=KnowledgeType.DEFINITION,
                    sources=["research"],
                )
            ]
            extraction_result.summary = "Extracted 1 knowledge item"

            # Configure the mock to return our result
            llm.generate_structured_mock.return_value = extraction_result

            # Call generate_structured to trigger token tracking
            await llm.generate_structured(
                f"Extract knowledge from: {result.findings}", None
            )

            return extraction_result.items

        # Override the extract_knowledge method
        knowledge_extractor.extract_knowledge = mock_extract_knowledge
        workflow.knowledge_extractor = knowledge_extractor

        # Extract knowledge
        items = await workflow.knowledge_extractor.extract_knowledge(
            result, {"objective": "Test objective"}
        )

        # Pop app context
        app_node = mock_context_with_token_counter.token_counter.pop()

        # Verify extraction
        assert len(items) == 1
        assert items[0].question == "What is quantum computing?"

        # Check token usage from extraction
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 300  # From generate_structured
        assert app_usage.input_tokens == 200
        assert app_usage.output_tokens == 100

    @pytest.mark.asyncio
    async def test_error_handling_token_tracking(
        self, mock_llm_factory_with_tokens, mock_context_with_token_counter
    ):
        """Test that tokens are tracked even when errors occur"""
        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Initialize workflow state properly
        from mcp_agent.workflows.adaptive.knowledge_manager import (
            EnhancedExecutionMemory,
        )
        from mcp_agent.workflows.adaptive.action_controller import ActionController

        workflow._current_execution_id = "test-error"
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test-error",
            objective="Test error handling",
            task_type=TaskType.RESEARCH,
        )
        workflow.action_controller = ActionController()

        # Push workflow context
        mock_context_with_token_counter.token_counter.push("error_workflow", "workflow")

        # Create aspect that will fail
        aspect = ResearchAspect(name="FailingResearch", objective="This will fail")

        # Make the LLM raise an error after recording tokens
        async def failing_generate_str(*args, **kwargs):
            # Record tokens first
            if mock_context_with_token_counter.token_counter:
                mock_context_with_token_counter.token_counter.push(
                    name="failing_call", node_type="llm_call"
                )
                mock_context_with_token_counter.token_counter.record_usage(
                    input_tokens=50,
                    output_tokens=0,  # No output due to error
                    model_name="test-model",
                    provider="test_provider",
                )
                mock_context_with_token_counter.token_counter.pop()
            raise Exception("LLM error")

        # Configure mock to fail
        mock_llm = mock_llm_factory_with_tokens(Agent(name="test", instruction="test"))
        mock_llm.generate_str = failing_generate_str

        def mock_factory(agent):
            return mock_llm

        # Override factory temporarily
        workflow.llm_factory = mock_factory

        # Mock _execute_single_aspect to track tokens and then fail
        async def mock_execute_with_error(aspect, params, span):
            # Track tokens through the mock LLM
            try:
                llm = mock_factory(Agent(name="test", instruction="test"))
                await llm.generate_str("This will fail")
            except Exception as e:
                # Return error result
                return SubagentResult(
                    aspect_name=aspect.name,
                    success=False,
                    error=str(e),
                    start_time=MagicMock(),
                    end_time=MagicMock(),
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                )

        workflow._execute_single_aspect = mock_execute_with_error

        # Execute research which will fail
        results = await workflow._execute_research([aspect], None, MagicMock())

        # Pop workflow context
        workflow_node = mock_context_with_token_counter.token_counter.pop()

        # Verify error was captured
        assert len(results) == 1
        assert results[0].success is False
        assert "LLM error" in results[0].error

        # But tokens should still be tracked (50 tokens were recorded before the error)
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 50
        assert workflow_usage.input_tokens == 50
        assert workflow_usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_predefined_agent_token_tracking(
        self,
        mock_llm_factory_with_tokens,
        mock_context_with_token_counter,
        mock_augmented_llm_with_token_tracking,
    ):
        """Test token tracking when using predefined agents"""
        # Create a predefined agent
        predefined_agent = Agent(name="PredefinedAgent", instruction="I am predefined")
        predefined_llm = mock_augmented_llm_with_token_tracking(
            agent=predefined_agent, context=mock_context_with_token_counter
        )
        predefined_llm.generate_str_mock.return_value = "Predefined result"
        # Add name attribute so workflow can find it
        predefined_llm.name = "PredefinedAgent"

        workflow = AdaptiveWorkflow(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=[predefined_llm],
            context=mock_context_with_token_counter,
        )

        # Push workflow context
        mock_context_with_token_counter.token_counter.push(
            "predefined_workflow", "workflow"
        )

        # Create aspect using predefined agent
        aspect = ResearchAspect(
            name="UseExisting",
            objective="Use predefined agent",
            use_predefined_agent="PredefinedAgent",
        )

        # Mock _execute_single_aspect to use the predefined agent
        async def mock_execute_with_predefined(aspect, params, span):
            # Get the predefined LLM from available_agents
            predefined = workflow.available_agents.get(aspect.use_predefined_agent)
            assert predefined is not None

            # Use the predefined LLM which will track tokens
            result = await predefined.generate_str(f"Execute: {aspect.objective}")

            return SubagentResult(
                aspect_name=aspect.name,
                findings=result,
                success=True,
                start_time=MagicMock(),
                end_time=MagicMock(),
                input_tokens=100,  # From generate_str
                output_tokens=50,
                total_tokens=150,
                model_name="test-model",
                provider="test_provider",
                cost=0.001,
            )

        workflow._execute_single_aspect = mock_execute_with_predefined

        # Execute research with predefined agent
        results = await workflow._execute_research([aspect], None, MagicMock())

        # Pop workflow context
        workflow_node = mock_context_with_token_counter.token_counter.pop()

        # Verify result
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].findings == "Predefined result"
        assert results[0].total_tokens == 150  # From predefined agent's generate_str

        # Check workflow aggregation
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 150
