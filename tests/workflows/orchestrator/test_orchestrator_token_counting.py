import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.orchestrator.orchestrator_models import (
    Plan,
    Step,
    NextStep,
    PlanResult,
    StepResult,
    AgentTask,
)
from mcp_agent.tracing.token_counter import TokenCounter
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class TestOrchestratorTokenCounting:
    """Tests for token counting in the Orchestrator workflow"""

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
        context = MagicMock()
        context.server_registry = MagicMock()
        context.server_registry.get_server_config.return_value = MagicMock(
            description="Test Server"
        )
        context.executor = MagicMock()
        context.executor.execute = AsyncMock()
        context.executor.execute_many = AsyncMock()
        context.model_selector = MagicMock()
        context.model_selector.select_model = MagicMock(return_value="test-model")
        context.tracer = None
        context.tracing_enabled = False

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

            async def generate(self, message, request_params=None):
                # Simulate token recording when the mock is called
                if self.context and self.context.token_counter:
                    # Push context for this LLM call
                    await self.context.token_counter.push(
                        name=f"llm_call_{self.agent.name}", node_type="llm_call"
                    )
                    # Record some token usage
                    await self.context.token_counter.record_usage(
                        input_tokens=100,
                        output_tokens=50,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    # Pop context
                    await self.context.token_counter.pop()

                return await self.generate_mock(message, request_params)

            async def generate_str(self, message, request_params=None):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"llm_call_str_{self.agent.name}", node_type="llm_call"
                    )
                    await self.context.token_counter.record_usage(
                        input_tokens=80,
                        output_tokens=40,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                # Return a result based on the agent
                if hasattr(self.agent, "name"):
                    return f"Result from {self.agent.name}"
                return await self.generate_str_mock(message, request_params)

            async def generate_structured(
                self, message, response_model, request_params=None
            ):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"llm_call_structured_{self.agent.name}",
                        node_type="llm_call",
                    )
                    await self.context.token_counter.record_usage(
                        input_tokens=120,
                        output_tokens=60,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                return await self.generate_structured_mock(
                    message, response_model, request_params
                )

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
            # Set up default mocks
            llm.generate_mock.return_value = ["Generated response"]
            llm.generate_str_mock.return_value = "Generated string response"
            llm.generate_structured_mock.return_value = MagicMock()
            return llm

        return factory

    @pytest.fixture
    def mock_agents(
        self, mock_context_with_token_counter, mock_augmented_llm_with_token_tracking
    ):
        """Create mock agents for testing"""
        agents = []
        for i, name in enumerate(["test_agent_1", "test_agent_2"], 1):
            agent = MagicMock(spec=Agent)
            agent.name = name
            agent.instruction = f"Test agent {i} instruction"
            agent.server_names = [f"test_server_{i}"]
            agent.context = None
            agent.initialized = False

            # Mock the async context manager methods
            async def mock_aenter(self=agent):
                # Simulate agent initialization
                self.initialized = True
                if not self.context:
                    self.context = mock_context_with_token_counter
                return self

            async def mock_aexit(self, *args):
                pass

            # Mock attach_llm to return a proper tracking LLM
            async def mock_attach_llm(llm_factory, self=agent):
                # Create an LLM that tracks tokens
                llm = mock_augmented_llm_with_token_tracking(
                    agent=self, context=mock_context_with_token_counter
                )
                llm.generate_str_mock.return_value = f"Result from {self.name}"
                return llm

            agent.__aenter__ = mock_aenter
            agent.__aexit__ = mock_aexit
            agent.attach_llm = mock_attach_llm

            agents.append(agent)

        return agents

    @pytest.mark.asyncio
    async def test_orchestrator_token_tracking_full_plan(
        self, mock_llm_factory_with_tokens, mock_agents, mock_context_with_token_counter
    ):
        """Test that token usage is tracked correctly for full plan orchestration"""
        # Create orchestrator
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
            plan_type="full",
        )

        # Mock the planner to return a plan with steps
        sample_plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[
                        AgentTask(description="Task 1", agent="test_agent_1"),
                        AgentTask(description="Task 2", agent="test_agent_2"),
                    ],
                )
            ],
            is_complete=False,
        )

        # Set up planner mock to return the plan twice:
        # 1. First call returns the plan with steps (not complete)
        # 2. Second call returns a complete plan (after steps are executed)
        call_count = 0

        async def planner_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call - return plan with steps to execute
                return sample_plan
            else:
                # Second call - return empty plan marked as complete
                return Plan(steps=[], is_complete=True)

        orchestrator.planner.generate_structured_mock.side_effect = planner_side_effect

        # Mock the executor to handle task execution
        # The executor should actually await the coroutines to trigger token tracking
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                # Each task is an llm.generate_str() coroutine
                result = await task
                results.append(result)
            return results

        orchestrator.executor.execute_many = AsyncMock(side_effect=mock_execute_many)

        # Push app context
        await mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Execute orchestration via generate() to trigger the @track_tokens decorator
        messages = await orchestrator.generate("Test objective")

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify results
        assert len(messages) == 1
        assert messages[0] == "Result from LLM Orchestration Synthesizer"

        # Check token usage
        summary = await mock_context_with_token_counter.token_counter.get_summary()

        # Now that agents don't push their own contexts, we should see:
        # 1. First planner call (generate_structured) - 180 tokens (120 input + 60 output)
        # 2. Task executions (2 agents x generate_str) - 2 x 120 tokens = 240 (160 input + 80 output)
        # 3. Second planner call (generate_structured) - 180 tokens (120 input + 60 output)
        # 4. Synthesizer call (generate_str) - 120 tokens (80 input + 40 output)
        # Total: 720 tokens
        assert summary.usage.total_tokens == 720
        assert summary.usage.input_tokens == 480  # 120*2 + 80*3
        assert summary.usage.output_tokens == 240  # 60*2 + 40*3

        # Check app node aggregation
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 720

        # Verify token hierarchy - the app node should have a agent child
        assert len(app_node.children) >= 1

        # Find the Orchestrator agent node
        orchestrator_node = None
        for child in app_node.children:
            if child.node_type == "agent" and "Orchestrator" in child.name:
                orchestrator_node = child
                break

        assert orchestrator_node is not None, (
            "Orchestrator agent node not found in hierarchy"
        )

        # The Orchestrator agent node should have the same token count as the app
        orchestrator_usage = orchestrator_node.aggregate_usage()
        assert orchestrator_usage.total_tokens == 720
        assert orchestrator_usage.input_tokens == 480
        assert orchestrator_usage.output_tokens == 240

        # Regression: planner/synthesizer nodes should have non-zero totals and sum(children) <= parent
        child_totals = 0
        planner_seen = False
        synthesizer_seen = False
        for child in orchestrator_node.children:
            usage = child.aggregate_usage()
            child_totals += usage.total_tokens
            if "Planner" in child.name:
                planner_seen = True
                assert usage.total_tokens > 0
            if "Synthesizer" in child.name:
                synthesizer_seen = True
                assert usage.total_tokens > 0
        assert planner_seen, "Planner node not found under orchestrator"
        assert synthesizer_seen, "Synthesizer node not found under orchestrator"
        assert child_totals <= orchestrator_usage.total_tokens

    @pytest.mark.asyncio
    async def test_orchestrator_token_tracking_iterative_plan(
        self, mock_llm_factory_with_tokens, mock_agents, mock_context_with_token_counter
    ):
        """Test that token usage is tracked correctly for iterative plan orchestration"""
        # Create orchestrator with iterative plan type
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
            plan_type="iterative",
        )

        # Mock the planner to return next steps
        next_step_1 = NextStep(
            description="Step 1",
            tasks=[AgentTask(description="Task 1", agent="test_agent_1")],
            is_complete=False,
        )

        next_step_2 = NextStep(
            description="Step 2",
            tasks=[AgentTask(description="Task 2", agent="test_agent_2")],
            is_complete=True,  # Mark as complete to end iteration
        )

        orchestrator.planner.generate_structured_mock.side_effect = [
            next_step_1,
            next_step_2,
        ]

        # The synthesizer is already created by the factory and will return the expected result

        # Mock _execute_step
        orchestrator._execute_step = AsyncMock(
            return_value=StepResult(
                step=Step(description="Step", tasks=[]),
                task_results=[],
                result="Step completed",
            )
        )

        # Push app context
        await mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Execute orchestration via generate()
        messages = await orchestrator.generate("Test objective")

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify results
        assert len(messages) == 1
        assert messages[0] == "Result from LLM Orchestration Synthesizer"

        # Check token usage
        # Should have tracked tokens from:
        # 1. Planner calls (generate_structured) - 2 calls x 180 tokens each = 360
        # 2. Synthesizer call (generate_str) - 120 tokens
        # Total: 480 tokens (no step execution in this test)
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 480
        assert summary.usage.input_tokens == 320  # 120*2 + 80
        assert summary.usage.output_tokens == 160  # 60*2 + 40

        # Check app node aggregation
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 480

        # Verify token hierarchy
        assert len(app_node.children) >= 1

        # Find the Orchestrator agent node
        orchestrator_node = None
        for child in app_node.children:
            if child.node_type == "agent" and "Orchestrator" in child.name:
                orchestrator_node = child
                break

        assert orchestrator_node is not None, (
            "Orchestrator agent node not found in hierarchy"
        )

        # The Orchestrator agent node should have the same token count
        orchestrator_usage = orchestrator_node.aggregate_usage()
        assert orchestrator_usage.total_tokens == 480
        assert orchestrator_usage.input_tokens == 320
        assert orchestrator_usage.output_tokens == 160

    @pytest.mark.asyncio
    async def test_orchestrator_nested_token_tracking(
        self, mock_llm_factory_with_tokens, mock_agents, mock_context_with_token_counter
    ):
        """Test token tracking with nested orchestrator contexts"""
        # Push app context
        await mock_context_with_token_counter.token_counter.push("main_app", "app")

        # Create first orchestrator
        orchestrator1 = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
            name="orchestrator_1",
        )

        # Mock simple plan completion
        orchestrator1.planner.generate_structured_mock.return_value = Plan(
            steps=[], is_complete=True
        )
        orchestrator1.synthesizer.generate_str_mock.return_value = "Result 1"

        # Push orchestrator 1 context
        await mock_context_with_token_counter.token_counter.push(
            "orchestrator_1", "agent"
        )

        # Execute first orchestrator
        await orchestrator1.execute(objective="Objective 1")

        # Pop orchestrator 1 context
        orch1_node = await mock_context_with_token_counter.token_counter.pop()

        # Create second orchestrator
        orchestrator2 = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
            name="orchestrator_2",
        )

        # Mock simple plan completion
        orchestrator2.planner.generate_structured_mock.return_value = Plan(
            steps=[], is_complete=True
        )
        orchestrator2.synthesizer.generate_str_mock.return_value = "Result 2"

        # Push orchestrator 2 context
        await mock_context_with_token_counter.token_counter.push(
            "orchestrator_2", "agent"
        )

        # Execute second orchestrator
        await orchestrator2.execute(objective="Objective 2")

        # Pop orchestrator 2 context
        orch2_node = await mock_context_with_token_counter.token_counter.pop()

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify individual orchestrator token usage
        orch1_usage = orch1_node.aggregate_usage()
        assert orch1_usage.total_tokens == 300  # 180 + 120

        orch2_usage = orch2_node.aggregate_usage()
        assert orch2_usage.total_tokens == 300  # 180 + 120

        # Verify app-level aggregation
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 600  # Total from both orchestrators

        # Check global summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 600
        assert "test-model (test_provider)" in summary.model_usage

    @pytest.mark.asyncio
    async def test_orchestrator_task_execution_token_tracking(
        self, mock_llm_factory_with_tokens, mock_agents, mock_context_with_token_counter
    ):
        """Test token tracking during task execution with multiple agents"""
        # Create orchestrator
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
        )

        # Create a step with multiple tasks
        test_step = Step(
            description="Multi-agent step",
            tasks=[
                AgentTask(description="Analyze data", agent="test_agent_1"),
                AgentTask(description="Generate report", agent="test_agent_2"),
            ],
        )

        # Mock executor.execute_many to track parallel execution
        async def mock_execute_many(tasks):
            results = []
            for i, task in enumerate(tasks):
                # Each task execution records tokens
                await mock_context_with_token_counter.token_counter.push(
                    name=f"task_{i}", node_type="task"
                )
                await mock_context_with_token_counter.token_counter.record_usage(
                    input_tokens=150 + i * 50,  # Vary tokens per task
                    output_tokens=75 + i * 25,
                    model_name="test-model",
                    provider="test_provider",
                )
                await mock_context_with_token_counter.token_counter.pop()
                results.append(f"Result from task {i}")
            return results

        orchestrator.executor.execute_many = AsyncMock(side_effect=mock_execute_many)

        # Push orchestrator context
        await mock_context_with_token_counter.token_counter.push(
            "orchestrator", "agent"
        )

        # Execute the step
        plan_result = PlanResult(objective="Test objective", step_results=[])
        step_result = await orchestrator._execute_step(
            step=test_step, previous_result=plan_result
        )

        # Pop orchestrator context
        orch_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify step result
        assert len(step_result.task_results) == 2
        assert step_result.task_results[0].result == "Result from task 0"
        assert step_result.task_results[1].result == "Result from task 1"

        # Check token usage
        # Task 0: 150 + 75 = 225 tokens
        # Task 1: 200 + 100 = 300 tokens
        # Total: 525 tokens
        orch_usage = orch_node.aggregate_usage()
        assert orch_usage.total_tokens == 525
        assert orch_usage.input_tokens == 350  # 150 + 200
        assert orch_usage.output_tokens == 175  # 75 + 100

    @pytest.mark.asyncio
    async def test_orchestrator_error_handling_token_tracking(
        self, mock_llm_factory_with_tokens, mock_agents, mock_context_with_token_counter
    ):
        """Test that token tracking works correctly even when errors occur"""
        # Create orchestrator
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory_with_tokens,
            available_agents=mock_agents,
            context=mock_context_with_token_counter,
        )

        # Mock planner to record tokens then raise an error
        async def planner_with_error(*args, **kwargs):
            # Record some tokens before error
            await mock_context_with_token_counter.token_counter.push(
                name="planner_error", node_type="llm_call"
            )
            await mock_context_with_token_counter.token_counter.record_usage(
                input_tokens=100,
                output_tokens=50,
                model_name="test-model",
                provider="test_provider",
            )
            await mock_context_with_token_counter.token_counter.pop()
            raise Exception("Planner error")

        orchestrator.planner.generate_structured = AsyncMock(
            side_effect=planner_with_error
        )

        # Push orchestrator context
        await mock_context_with_token_counter.token_counter.push(
            "orchestrator", "agent"
        )

        # Execute orchestration (should raise error)
        with pytest.raises(Exception, match="Planner error"):
            await orchestrator.execute(objective="Test objective")

        # Pop orchestrator context
        orch_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify tokens were still tracked before the error
        orch_usage = orch_node.aggregate_usage()
        assert orch_usage.total_tokens == 150
        assert orch_usage.input_tokens == 100
        assert orch_usage.output_tokens == 50

        # Check global summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 150
