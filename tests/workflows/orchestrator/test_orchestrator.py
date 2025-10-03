import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.orchestrator.orchestrator_models import (
    Plan,
    Step,
    NextStep,
    PlanResult,
    StepResult,
    AgentTask,
    TaskWithResult,
)


class TestOrchestratorInit:
    """Tests for Orchestrator initialization"""

    def test_init_with_defaults(self, mock_llm_factory, mock_context):
        """Test that the Orchestrator can be initialized with default values"""
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        assert orchestrator.llm_factory == mock_llm_factory
        assert orchestrator.context == mock_context
        assert orchestrator.plan_type == "full"
        assert orchestrator.agents == {}
        assert orchestrator.default_request_params.use_history is False
        assert orchestrator.default_request_params.maxTokens == 16384

    def test_init_with_planner(self, mock_llm_factory, mock_context):
        """Test that the Orchestrator can be initialized with a custom planner"""
        planner = MagicMock()

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory, planner=planner, context=mock_context
        )

        assert orchestrator.planner == planner

    def test_init_with_agents(self, mock_llm_factory, mock_agents, mock_context):
        """Test that the Orchestrator can be initialized with agents"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
        )

        assert len(orchestrator.agents) == 2
        assert "test_agent_1" in orchestrator.agents
        assert "test_agent_2" in orchestrator.agents

    def test_init_with_iterative_plan_type(self, mock_llm_factory, mock_context):
        """Test that the Orchestrator can be initialized with iterative plan type"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory, plan_type="iterative", context=mock_context
        )

        assert orchestrator.plan_type == "iterative"

    def test_init_with_invalid_plan_type(self, mock_llm_factory, mock_context):
        """Test that the Orchestrator rejects invalid plan_type parameter"""
        with pytest.raises(ValueError):
            Orchestrator(
                llm_factory=mock_llm_factory, plan_type="invalid", context=mock_context
            )


@pytest.mark.asyncio
class TestOrchestratorMethods:
    """Tests for Orchestrator methods"""

    async def test_generate(self, mock_llm_factory, mock_context, sample_plan_result):
        """Test that generate calls execute and returns the result"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        # Mock the execute method
        orchestrator.execute = AsyncMock(return_value=sample_plan_result)

        # Call generate
        result = await orchestrator.generate("Test objective")

        # Check that execute was called once
        assert orchestrator.execute.call_count == 1

        # Extract the call arguments
        call_args = orchestrator.execute.call_args
        args, kwargs = call_args

        # Check the arguments
        assert kwargs.get("objective") == "Test objective"
        assert isinstance(kwargs.get("request_params"), RequestParams)

        # Check that the result is a list containing the plan result
        assert isinstance(result, list)
        assert result[0] == sample_plan_result.result

    async def test_generate_str(
        self, mock_llm_factory, mock_context, sample_plan_result
    ):
        """Test that generate_str calls generate and returns a string"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        # Mock the generate method
        sample_plan_result.result = "Test result"
        orchestrator.generate = AsyncMock(return_value=[sample_plan_result.result])

        # Call generate_str
        result = await orchestrator.generate_str("Test objective")

        # Check that generate was called once
        assert orchestrator.generate.call_count == 1

        # Extract the call arguments
        call_args = orchestrator.generate.call_args
        args, kwargs = call_args

        # Check the arguments
        assert kwargs.get("message") == "Test objective"
        assert isinstance(kwargs.get("request_params"), RequestParams)

        # Check that the result is the string representation of the plan result
        assert result == "Test result"

    # TODO: Fix this
    # async def test_generate_structured(self, mock_llm_factory, mock_context):
    #     """Test that generate_structured calls generate_str and returns a structured result"""
    #     # Create the orchestrator
    #     orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

    #     # Mock the generate_str method to return a test result
    #     orchestrator.generate_str = AsyncMock(return_value="Test result")

    #     # Call generate_structured
    #     result = await orchestrator.generate_structured(
    #         message="Test objective", response_model=str
    #     )

    #     # Check that generate_str was called once
    #     assert orchestrator.generate_str.call_count == 1

    #     # Extract the call arguments
    #     call_args = orchestrator.generate_str.call_args
    #     args, kwargs = call_args

    #     # Check the arguments
    #     assert kwargs.get("message") == "Test objective"
    #     assert isinstance(kwargs.get("request_params"), RequestParams)

    #     # Check that the result is the structured result
    #     assert result == "Structured result"

    async def test_execute_step(
        self,
        mock_llm_factory,
        mock_agents,
        mock_context,
        sample_step,
        sample_plan_result,
    ):
        """Test that _execute_step executes a step and returns a StepResult"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
        )

        # Create a mock LLM for each agent
        mock_llms = {}
        for agent_name, agent in orchestrator.agents.items():
            mock_llm = MagicMock()
            mock_llm.generate_str = AsyncMock(return_value=f"Result from {agent_name}")
            mock_llms[agent_name] = mock_llm

        # Mock the LLM factory to return the appropriate mock LLM
        mock_llm_factory.side_effect = lambda agent: mock_llms.get(
            agent.name, MagicMock()
        )

        # Create a mock executor
        orchestrator.executor = MagicMock()
        # Mock the execute_many method to return the agent results
        orchestrator.executor.execute_many = AsyncMock(
            return_value=[f"Result from {task.agent}" for task in sample_step.tasks]
        )

        # Call _execute_step
        result = await orchestrator._execute_step(
            step=sample_step, previous_result=sample_plan_result
        )

        # Check that the executor was called
        orchestrator.executor.execute_many.assert_called_once()

        # Check that the result is a StepResult
        assert isinstance(result, StepResult)
        assert result.step == sample_step
        assert len(result.task_results) == 2
        assert result.task_results[0].result == "Result from test_agent_1"
        assert result.task_results[1].result == "Result from test_agent_2"

    async def test_get_full_plan(
        self, mock_llm_factory, mock_agents, mock_context, sample_plan
    ):
        """Test that _get_full_plan generates a full plan"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
        )

        # Create a mock planner
        orchestrator.planner = MagicMock()
        orchestrator.planner.generate_structured = AsyncMock(return_value=sample_plan)

        # Call _get_full_plan
        plan_result = PlanResult(objective="Test objective", step_results=[])
        result = await orchestrator._get_full_plan(
            objective="Test objective", plan_result=plan_result
        )

        # Check that the planner's generate_structured was called
        orchestrator.planner.generate_structured.assert_called_once()

        # Check that the result is the sample plan
        assert result == sample_plan

    async def test_get_next_step(self, mock_llm_factory, mock_agents, mock_context):
        """Test that _get_next_step generates the next step"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
        )

        # Create a mock planner
        orchestrator.planner = MagicMock()
        next_step = NextStep(
            description="Next step",
            tasks=[AgentTask(description="Next task", agent="test_agent_1")],
            is_complete=False,
        )
        orchestrator.planner.generate_structured = AsyncMock(return_value=next_step)

        # Call _get_next_step
        plan_result = PlanResult(objective="Test objective", step_results=[])
        result = await orchestrator._get_next_step(
            objective="Test objective", plan_result=plan_result
        )

        # Check that the planner's generate_structured was called
        orchestrator.planner.generate_structured.assert_called_once()

        # Check that the result is the next step
        assert result == next_step

    async def test_execute_full_plan(
        self,
        mock_llm_factory,
        mock_agents,
        mock_context,
        sample_plan,
        sample_step_result,
    ):
        """Test that execute executes a full plan"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # First create the mocks
        # We need to ensure the plan is NOT complete so steps get executed
        sample_plan.is_complete = False

        # Create a copy of the plan to return from the mock
        plan_copy = Plan(
            steps=sample_plan.steps.copy(),
            is_complete=False,  # Plan must not be complete initially so steps get executed
        )

        # After execute_step is called, we'll make the plan complete
        # This is done using a side effect on mock_execute_step
        def set_plan_complete_after_step(*args, **kwargs):
            # After the step is executed, mark the plan as complete
            plan_copy.is_complete = True
            return sample_step_result

        mock_get_full_plan = AsyncMock(return_value=plan_copy)
        mock_execute_step = AsyncMock(side_effect=set_plan_complete_after_step)
        mock_planner = MagicMock()
        mock_planner.generate_str = AsyncMock(return_value="Final result")

        # Use patching to mock the methods on the Orchestrator class
        with patch.object(Orchestrator, "_get_full_plan", mock_get_full_plan):
            with patch.object(Orchestrator, "_execute_step", mock_execute_step):
                # Create the orchestrator instance
                orchestrator = Orchestrator(
                    llm_factory=mock_llm_factory,
                    available_agents=mock_agents,
                    context=mock_context,
                    plan_type="full",
                )

                # Set the planner and synthesizer
                orchestrator.planner = mock_planner
                orchestrator.synthesizer = MagicMock()
                orchestrator.synthesizer.generate_str = AsyncMock(
                    return_value="Final result"
                )

                # Call execute
                result = await orchestrator.execute(objective="Test objective")

        # Check that _get_full_plan was called twice
        mock_get_full_plan.assert_called()

        # Sample plan has steps, so ensure _execute_step was called
        # once for each step in the plan
        assert len(sample_plan.steps) == 1
        assert mock_execute_step.call_count == 1

        # Check that the synthesizer's generate_str was called
        orchestrator.synthesizer.generate_str.assert_called_once()

        # Check that the result is a PlanResult with is_complete=True and the final result
        assert isinstance(result, PlanResult)
        assert result.is_complete
        assert result.result == "Final result"

    async def test_execute_iterative_plan(
        self, mock_llm_factory, mock_agents, mock_context, sample_step_result
    ):
        """Test that execute executes an iterative plan"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # First create the mocks
        # Create next steps that will be returned by _get_next_step
        next_step_1 = NextStep(
            description="Step 1",
            tasks=[AgentTask(description="Task 1", agent="test_agent_1")],
            is_complete=False,
        )
        next_step_2 = NextStep(
            description="Step 2",
            tasks=[AgentTask(description="Task 2", agent="test_agent_2")],
            is_complete=True,
        )

        # Create the mocks
        mock_get_next_step = AsyncMock(side_effect=[next_step_1, next_step_2])
        mock_execute_step = AsyncMock(return_value=sample_step_result)
        mock_planner = MagicMock()
        mock_planner.generate_str = AsyncMock(return_value="Final result")

        # Use patching to mock the methods on the Orchestrator class
        with patch.object(Orchestrator, "_get_next_step", mock_get_next_step):
            with patch.object(Orchestrator, "_execute_step", mock_execute_step):
                # Create the orchestrator instance
                orchestrator = Orchestrator(
                    llm_factory=mock_llm_factory,
                    available_agents=mock_agents,
                    context=mock_context,
                    plan_type="iterative",
                )

                # Set the planner and synthesizer
                orchestrator.planner = mock_planner
                orchestrator.synthesizer = MagicMock()
                orchestrator.synthesizer.generate_str = AsyncMock(
                    return_value="Final result"
                )

                # Call execute
                result = await orchestrator.execute(objective="Test objective")

        # Check that _get_next_step was called twice
        assert mock_get_next_step.call_count == 2

        # Check that _execute_step was called once
        assert mock_execute_step.call_count == 1

        # Check that the synthesizer's generate_str was called to synthesize the result
        orchestrator.synthesizer.generate_str.assert_called_once()

        # Check that the result is a PlanResult with is_complete=True and the final result
        assert isinstance(result, PlanResult)
        assert result.is_complete
        assert result.result == "Final result"

    async def test_execute_max_iterations(
        self, mock_llm_factory, mock_agents, mock_context
    ):
        """Test that execute raises an error when max iterations is reached"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Create a next step that is never complete
        next_step = NextStep(
            description="Never-ending step",
            tasks=[AgentTask(description="Never-ending task", agent="test_agent_1")],
            is_complete=False,
        )

        # Create a plan that is never complete
        plan = Plan(steps=[next_step], is_complete=False)

        # Create a step result for the never-ending step
        step_result = StepResult(
            step=Step(
                description="Never-ending step",
                tasks=[
                    AgentTask(description="Never-ending task", agent="test_agent_1")
                ],
            ),
            task_results=[
                TaskWithResult(
                    description="Never-ending task",
                    agent="test_agent_1",
                    result="Step result",
                )
            ],
            result="Step result",
        )

        # Create the mocks
        mock_get_full_plan = AsyncMock(return_value=plan)
        mock_execute_step = AsyncMock(return_value=step_result)

        # Use patching to mock the methods on the Orchestrator class
        with patch.object(Orchestrator, "_get_full_plan", mock_get_full_plan):
            with patch.object(Orchestrator, "_execute_step", mock_execute_step):
                # Create the orchestrator instance
                orchestrator = Orchestrator(
                    llm_factory=mock_llm_factory,
                    available_agents=mock_agents,
                    context=mock_context,
                )

                # Set max_iterations to a low value
                request_params = RequestParams(max_iterations=2)

                # Check that execute raises an error
                with pytest.raises(RuntimeError):
                    await orchestrator.execute(
                        objective="Test objective", request_params=request_params
                    )

                # Check that _get_full_plan was called
                assert mock_get_full_plan.call_count >= 1

                # Check that _execute_step was called for the max number of iterations
                assert mock_execute_step.call_count == 2

    async def test_format_agent_info(self, mock_llm_factory, mock_agents, mock_context):
        """Test that _format_agent_info formats agent information correctly"""
        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
        )

        # Call _format_agent_info
        result = orchestrator._format_agent_info("test_agent_1")

        # Check that the result contains the agent name and instruction
        assert "test_agent_1" in result
        assert "Test agent 1 instruction" in result

    async def test_format_server_info(self, mock_llm_factory, mock_context):
        """Test that _format_server_info formats server information correctly"""
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        # Call _format_server_info
        result = orchestrator._format_server_info("test_server")

        # Check that the result contains the server name
        assert "test_server" in result

    async def test_execute_step_with_missing_agent(
        self, mock_llm_factory, mock_context, sample_step, sample_plan_result
    ):
        """Test that _execute_step raises an error when an agent is missing"""
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        # Call _execute_step with a step that requires an agent that doesn't exist
        with pytest.raises(ValueError):
            await orchestrator._execute_step(
                step=sample_step, previous_result=sample_plan_result
            )

    async def test_generate_with_history(self, mock_llm_factory, mock_context):
        """Test that generate raises an error when history tracking is enabled"""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        orchestrator = Orchestrator(llm_factory=mock_llm_factory, context=mock_context)

        # Call generate with history tracking enabled
        request_params = RequestParams(use_history=True)

        # Check that generate raises an error
        with pytest.raises(NotImplementedError):
            await orchestrator.generate("Test objective", request_params=request_params)
