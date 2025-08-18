import pytest
from unittest.mock import MagicMock

from mcp_agent.workflows.orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorOverrides,
)
from mcp_agent.workflows.orchestrator.orchestrator_models import (
    PlanResult,
)


class TestOrchestratorOverrides:
    """Tests for OrchestratorOverrides dataclass"""

    def test_init_with_defaults(self):
        """Test that OrchestratorOverrides can be initialized with default values"""
        overrides = OrchestratorOverrides()

        assert overrides.orchestrator_instruction is None
        assert overrides.planner_instruction is None
        assert overrides.synthesizer_instruction is None
        assert overrides.get_full_plan_prompt is None
        assert overrides.get_iterative_plan_prompt is None
        assert overrides.get_task_prompt is None
        assert overrides.get_synthesize_plan_prompt is None

    def test_init_with_all_overrides(self):
        """Test that OrchestratorOverrides can be initialized with all overrides"""
        custom_orchestrator_instruction = "Custom orchestrator instruction"
        custom_planner_instruction = "Custom planner instruction"
        custom_synthesizer_instruction = "Custom synthesizer instruction"

        def custom_get_full_plan_prompt(objective, plan_result, agents):
            agent_count = len(agents) if agents else 0
            status = (
                "complete" if plan_result and plan_result.is_complete else "incomplete"
            )
            return f"Custom full plan prompt for {objective} (agents: {agent_count}, status: {status})"

        def custom_get_iterative_plan_prompt(objective, plan_result, agents):
            agent_count = len(agents) if agents else 0
            steps_completed = len(plan_result.step_results) if plan_result else 0
            return f"Custom iterative plan prompt for {objective} (agents: {agent_count}, steps done: {steps_completed})"

        def custom_get_task_prompt(objective, task, context):
            context_length = len(context) if context else 0
            return f"Custom task prompt for {task} (objective: {objective}, context chars: {context_length})"

        def custom_get_synthesize_plan_prompt(plan_result):
            steps_count = len(plan_result.step_results) if plan_result else 0
            return f"Custom synthesize plan prompt for {plan_result.objective} ({steps_count} steps completed)"

        overrides = OrchestratorOverrides(
            orchestrator_instruction=custom_orchestrator_instruction,
            planner_instruction=custom_planner_instruction,
            synthesizer_instruction=custom_synthesizer_instruction,
            get_full_plan_prompt=custom_get_full_plan_prompt,
            get_iterative_plan_prompt=custom_get_iterative_plan_prompt,
            get_task_prompt=custom_get_task_prompt,
            get_synthesize_plan_prompt=custom_get_synthesize_plan_prompt,
        )

        assert overrides.orchestrator_instruction == custom_orchestrator_instruction
        assert overrides.planner_instruction == custom_planner_instruction
        assert overrides.synthesizer_instruction == custom_synthesizer_instruction
        assert overrides.get_full_plan_prompt == custom_get_full_plan_prompt
        assert overrides.get_iterative_plan_prompt == custom_get_iterative_plan_prompt
        assert overrides.get_task_prompt == custom_get_task_prompt
        assert overrides.get_synthesize_plan_prompt == custom_get_synthesize_plan_prompt

        # Test that all custom functions work correctly with all their parameters
        test_plan_result = PlanResult(objective="test obj", step_results=[])
        test_agents = ["agent1", "agent2"]

        full_plan_result = custom_get_full_plan_prompt(
            "test objective", test_plan_result, test_agents
        )
        assert (
            "Custom full plan prompt for test objective (agents: 2, status: incomplete)"
            == full_plan_result
        )

        iterative_plan_result = custom_get_iterative_plan_prompt(
            "test objective", test_plan_result, test_agents
        )
        assert (
            "Custom iterative plan prompt for test objective (agents: 2, steps done: 0)"
            == iterative_plan_result
        )

        task_result = custom_get_task_prompt(
            "test objective", "test task", "context data"
        )
        assert (
            "Custom task prompt for test task (objective: test objective, context chars: 12)"
            == task_result
        )

        synthesize_result = custom_get_synthesize_plan_prompt(test_plan_result)
        assert (
            "Custom synthesize plan prompt for test obj (0 steps completed)"
            == synthesize_result
        )


class TestOrchestratorWithOverrides:
    """Tests for Orchestrator functionality with overrides applied"""

    def test_orchestrator_with_custom_orchestrator_instruction(
        self, mock_llm_factory, mock_context
    ):
        """Test that Orchestrator uses custom orchestrator instruction when provided"""
        custom_instruction = "Custom orchestrator instruction for testing"
        overrides = OrchestratorOverrides(orchestrator_instruction=custom_instruction)

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory, context=mock_context, overrides=overrides
        )

        assert orchestrator.agent.instruction == custom_instruction

    def test_orchestrator_with_custom_planner_instruction(
        self, mock_llm_factory, mock_context
    ):
        """Test that Orchestrator uses custom planner instruction when provided"""
        custom_instruction = "Custom planner instruction for testing"
        overrides = OrchestratorOverrides(planner_instruction=custom_instruction)

        # Create a mock LLM factory that tracks calls
        mock_factory = MagicMock(side_effect=mock_llm_factory)

        # Create orchestrator to trigger planner creation with custom instruction
        _ = Orchestrator(
            llm_factory=mock_factory, context=mock_context, overrides=overrides
        )

        # The planner should be created with the custom instruction
        # We can verify this by checking the agent passed to the llm_factory
        mock_factory.assert_called()
        # Get the planner creation call
        planner_agent_calls = [
            call
            for call in mock_factory.call_args_list
            if call[1]["agent"].name == "LLM Orchestration Planner"
        ]
        assert len(planner_agent_calls) > 0
        planner_agent = planner_agent_calls[0][1]["agent"]
        assert custom_instruction.strip() in planner_agent.instruction

    def test_orchestrator_with_custom_synthesizer_instruction(
        self, mock_llm_factory, mock_context
    ):
        """Test that Orchestrator uses custom synthesizer instruction when provided"""
        custom_instruction = "Custom synthesizer instruction for testing"
        overrides = OrchestratorOverrides(synthesizer_instruction=custom_instruction)

        # Create a mock LLM factory that tracks calls
        mock_factory = MagicMock(side_effect=mock_llm_factory)

        # Create orchestrator to trigger synthesizer creation with custom instruction
        _ = Orchestrator(
            llm_factory=mock_factory, context=mock_context, overrides=overrides
        )

        # The synthesizer should be created with the custom instruction
        # We can verify this by checking the agent passed to the llm_factory
        mock_factory.assert_called()
        # Get the synthesizer creation call
        synthesizer_agent_calls = [
            call
            for call in mock_factory.call_args_list
            if call[1]["agent"].name == "LLM Orchestration Synthesizer"
        ]
        assert len(synthesizer_agent_calls) > 0
        synthesizer_agent = synthesizer_agent_calls[0][1]["agent"]
        assert synthesizer_agent.instruction == custom_instruction

    def test_orchestrator_with_custom_full_plan_prompt(
        self, mock_llm_factory, mock_agents, mock_context
    ):
        """Test that Orchestrator stores custom full plan prompt correctly"""

        def custom_get_full_plan_prompt(objective, plan_result, agents):
            agent_count = len(agents) if agents else 0
            status = (
                "complete" if plan_result and plan_result.is_complete else "incomplete"
            )
            return f"CUSTOM FULL PLAN: {objective} (agents: {agent_count}, status: {status})"

        overrides = OrchestratorOverrides(
            get_full_plan_prompt=custom_get_full_plan_prompt
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
            overrides=overrides,
        )

        # Verify that the override was properly stored
        assert (
            orchestrator.overrides.get_full_plan_prompt == custom_get_full_plan_prompt
        )

        # Test that the custom function works correctly with all parameters
        test_plan_result = PlanResult(objective="test obj", step_results=[])
        test_prompt = orchestrator.overrides.get_full_plan_prompt(
            objective="test objective",
            plan_result=test_plan_result,
            agents=["agent1", "agent2"],
        )
        assert (
            test_prompt
            == "CUSTOM FULL PLAN: test objective (agents: 2, status: incomplete)"
        )

    def test_orchestrator_with_custom_iterative_plan_prompt(
        self, mock_llm_factory, mock_agents, mock_context
    ):
        """Test that Orchestrator stores custom iterative plan prompt correctly"""

        def custom_get_iterative_plan_prompt(objective, plan_result, agents):
            agent_count = len(agents) if agents else 0
            steps_completed = len(plan_result.step_results) if plan_result else 0
            return f"CUSTOM ITERATIVE PLAN: {objective} (agents: {agent_count}, steps done: {steps_completed})"

        overrides = OrchestratorOverrides(
            get_iterative_plan_prompt=custom_get_iterative_plan_prompt
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
            overrides=overrides,
        )

        # Verify that the override was properly stored
        assert (
            orchestrator.overrides.get_iterative_plan_prompt
            == custom_get_iterative_plan_prompt
        )

        # Test that the custom function works correctly with all parameters
        test_plan_result = PlanResult(objective="test obj", step_results=[])
        test_prompt = orchestrator.overrides.get_iterative_plan_prompt(
            objective="test objective",
            plan_result=test_plan_result,
            agents=["agent1", "agent2"],
        )
        assert (
            test_prompt
            == "CUSTOM ITERATIVE PLAN: test objective (agents: 2, steps done: 0)"
        )

    def test_orchestrator_with_custom_task_prompt(self, mock_llm_factory, mock_context):
        """Test that Orchestrator properly stores custom task prompt template"""

        def custom_get_task_prompt(objective, task, context):
            context_length = len(context) if context else 0
            return f"CUSTOM TASK: {task} (objective: {objective}, context chars: {context_length})"

        overrides = OrchestratorOverrides(get_task_prompt=custom_get_task_prompt)

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            context=mock_context,
            overrides=overrides,
        )

        # Verify that the override was properly stored
        assert orchestrator.overrides.get_task_prompt == custom_get_task_prompt

        # Test that the custom template function works correctly with all parameters
        test_prompt = orchestrator.overrides.get_task_prompt(
            objective="test objective", task="test task", context="context data"
        )
        assert (
            test_prompt
            == "CUSTOM TASK: test task (objective: test objective, context chars: 12)"
        )

    def test_orchestrator_with_custom_synthesize_plan_prompt(
        self, mock_llm_factory, mock_agents, mock_context
    ):
        """Test that Orchestrator stores custom synthesize plan prompt correctly"""

        def custom_get_synthesize_plan_prompt(plan_result):
            steps_count = len(plan_result.step_results) if plan_result else 0
            return f"CUSTOM SYNTHESIZE: {plan_result.objective} ({steps_count} steps completed)"

        overrides = OrchestratorOverrides(
            get_synthesize_plan_prompt=custom_get_synthesize_plan_prompt
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
            overrides=overrides,
        )

        # Verify that the override was properly stored
        assert (
            orchestrator.overrides.get_synthesize_plan_prompt
            == custom_get_synthesize_plan_prompt
        )

        # Test that the custom function works correctly with all parameters
        plan_result = PlanResult(objective="test objective", step_results=[])
        test_prompt = orchestrator.overrides.get_synthesize_plan_prompt(plan_result)
        assert test_prompt == "CUSTOM SYNTHESIZE: test objective (0 steps completed)"

    def test_orchestrator_with_no_overrides_uses_defaults(
        self, mock_llm_factory, mock_context
    ):
        """Test that Orchestrator uses default values when no overrides are provided"""
        # Create a mock LLM factory that tracks calls
        mock_factory = MagicMock(side_effect=mock_llm_factory)

        orchestrator = Orchestrator(llm_factory=mock_factory, context=mock_context)

        # Check that default orchestrator instruction is used
        assert (
            orchestrator.agent.instruction is not None
            and len(orchestrator.agent.instruction) > 0
        )

        # Check that the overrides object is created with defaults (all None)
        assert orchestrator.overrides is not None
        assert orchestrator.overrides.orchestrator_instruction is None
        assert orchestrator.overrides.planner_instruction is None
        assert orchestrator.overrides.synthesizer_instruction is None
        assert orchestrator.overrides.get_full_plan_prompt is None
        assert orchestrator.overrides.get_iterative_plan_prompt is None
        assert orchestrator.overrides.get_task_prompt is None
        assert orchestrator.overrides.get_synthesize_plan_prompt is None

        # Verify that the planner was created with the default instruction
        planner_agent_calls = [
            call
            for call in mock_factory.call_args_list
            if call[1]["agent"].name == "LLM Orchestration Planner"
        ]
        assert len(planner_agent_calls) > 0
        planner_agent = planner_agent_calls[0][1]["agent"]
        assert len(planner_agent.instruction) > 0

        # Verify that the synthesizer was created with the default instruction
        synthesizer_agent_calls = [
            call
            for call in mock_factory.call_args_list
            if call[1]["agent"].name == "LLM Orchestration Synthesizer"
        ]
        assert synthesizer_agent_calls is not None and len(synthesizer_agent_calls) > 0
        synthesizer_agent = synthesizer_agent_calls[0][1]["agent"]
        assert (
            synthesizer_agent.instruction is not None
            and len(synthesizer_agent.instruction) > 0
        )

    def test_orchestrator_with_partial_overrides(self, mock_llm_factory, mock_context):
        """Test that Orchestrator works correctly with partial overrides"""
        custom_orchestrator_instruction = "Custom orchestrator instruction"
        overrides = OrchestratorOverrides(
            orchestrator_instruction=custom_orchestrator_instruction,
            # Leave other overrides as None to test partial override behavior
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory, context=mock_context, overrides=overrides
        )

        # Check that the custom orchestrator instruction is used
        assert orchestrator.agent.instruction == custom_orchestrator_instruction

        # Check that other overrides remain None (should use defaults)
        assert orchestrator.overrides.planner_instruction is None
        assert orchestrator.overrides.synthesizer_instruction is None
        assert orchestrator.overrides.get_full_plan_prompt is None


class TestOrchestratorOverrideProtocols:
    """Tests for the protocol classes used in orchestrator overrides"""

    def test_custom_full_plan_prompt_function(self):
        """Test that custom full plan prompt function works correctly with all parameters"""

        def custom_full_plan_prompt(objective: str, plan_result, agents):
            agent_count = len(agents) if agents else 0
            status = (
                "complete" if plan_result and plan_result.is_complete else "incomplete"
            )
            return f"Custom prompt for {objective} (agents: {agent_count}, status: {status})"

        test_plan_result = PlanResult(objective="test obj", step_results=[])
        result = custom_full_plan_prompt(
            "test objective", test_plan_result, ["agent1", "agent2"]
        )
        assert (
            result == "Custom prompt for test objective (agents: 2, status: incomplete)"
        )

    def test_custom_iterative_plan_prompt_function(self):
        """Test that custom iterative plan prompt function works correctly with all parameters"""

        def custom_iterative_plan_prompt(objective: str, plan_result, agents):
            agent_count = len(agents) if agents else 0
            steps_completed = len(plan_result.step_results) if plan_result else 0
            return f"Custom iterative prompt for {objective} (agents: {agent_count}, steps done: {steps_completed})"

        test_plan_result = PlanResult(objective="test obj", step_results=[])
        result = custom_iterative_plan_prompt(
            "test objective", test_plan_result, ["agent1"]
        )
        assert (
            result
            == "Custom iterative prompt for test objective (agents: 1, steps done: 0)"
        )

    def test_custom_task_prompt_function(self):
        """Test that custom task prompt function works correctly with all parameters"""

        def custom_task_prompt(objective: str, task: str, context: str):
            context_length = len(context) if context else 0
            return f"Custom task prompt for {task} (objective: {objective}, context chars: {context_length})"

        result = custom_task_prompt("test objective", "test task", "context data")
        assert (
            result
            == "Custom task prompt for test task (objective: test objective, context chars: 12)"
        )

    def test_custom_synthesize_plan_prompt_function(self):
        """Test that custom synthesize plan prompt function works correctly with all parameters"""

        def custom_synthesize_plan_prompt(plan_result):
            steps_count = len(plan_result.step_results) if plan_result else 0
            return f"Custom synthesize prompt for {plan_result.objective} ({steps_count} steps completed)"

        plan_result = PlanResult(objective="test objective", step_results=[])
        result = custom_synthesize_plan_prompt(plan_result)
        assert (
            result == "Custom synthesize prompt for test objective (0 steps completed)"
        )


class TestOrchestratorOverridesIntegration:
    """Integration tests for orchestrator overrides with complex scenarios"""

    def test_orchestrator_overrides_end_to_end(
        self, mock_llm_factory, mock_agents, mock_context
    ):
        """Test that all overrides are stored correctly together"""
        custom_orchestrator_instruction = "Custom orchestrator for E2E test"
        custom_planner_instruction = "Custom planner for E2E test"
        custom_synthesizer_instruction = "Custom synthesizer for E2E test"

        def custom_get_full_plan_prompt(objective, plan_result, agents):
            agent_count = len(agents) if agents else 0
            status = (
                "complete" if plan_result and plan_result.is_complete else "incomplete"
            )
            return (
                f"E2E FULL PLAN: {objective} (agents: {agent_count}, status: {status})"
            )

        def custom_get_task_prompt(objective, task, context):
            context_length = len(context) if context else 0
            return f"E2E TASK: {task} (objective: {objective}, context chars: {context_length})"

        def custom_get_synthesize_plan_prompt(plan_result):
            steps_count = len(plan_result.step_results) if plan_result else 0
            return f"E2E SYNTHESIZE: {plan_result.objective} ({steps_count} steps completed)"

        overrides = OrchestratorOverrides(
            orchestrator_instruction=custom_orchestrator_instruction,
            planner_instruction=custom_planner_instruction,
            synthesizer_instruction=custom_synthesizer_instruction,
            get_full_plan_prompt=custom_get_full_plan_prompt,
            get_task_prompt=custom_get_task_prompt,
            get_synthesize_plan_prompt=custom_get_synthesize_plan_prompt,
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory,
            available_agents=mock_agents,
            context=mock_context,
            overrides=overrides,
        )

        # Verify that all custom instructions were applied
        assert orchestrator.agent.instruction == custom_orchestrator_instruction

        # Verify that all overrides were stored correctly
        assert (
            orchestrator.overrides.orchestrator_instruction
            == custom_orchestrator_instruction
        )
        assert orchestrator.overrides.planner_instruction == custom_planner_instruction
        assert (
            orchestrator.overrides.synthesizer_instruction
            == custom_synthesizer_instruction
        )
        assert (
            orchestrator.overrides.get_full_plan_prompt == custom_get_full_plan_prompt
        )
        assert orchestrator.overrides.get_task_prompt == custom_get_task_prompt
        assert (
            orchestrator.overrides.get_synthesize_plan_prompt
            == custom_get_synthesize_plan_prompt
        )

        # Test that all custom functions work correctly with all parameters
        test_plan_result = PlanResult(objective="test obj", step_results=[])

        full_plan_result = custom_get_full_plan_prompt(
            "test", test_plan_result, ["agent1", "agent2"]
        )
        assert full_plan_result == "E2E FULL PLAN: test (agents: 2, status: incomplete)"

        task_result = custom_get_task_prompt("test obj", "test task", "context data")
        assert (
            task_result
            == "E2E TASK: test task (objective: test obj, context chars: 12)"
        )

        synthesize_result = custom_get_synthesize_plan_prompt(test_plan_result)
        assert synthesize_result == "E2E SYNTHESIZE: test obj (0 steps completed)"

    def test_orchestrator_override_error_handling(self, mock_llm_factory, mock_context):
        """Test that orchestrator can store override functions that might error"""

        def faulty_get_full_plan_prompt(objective, plan_result, agents):
            raise ValueError("Custom prompt error")

        overrides = OrchestratorOverrides(
            get_full_plan_prompt=faulty_get_full_plan_prompt
        )

        orchestrator = Orchestrator(
            llm_factory=mock_llm_factory, context=mock_context, overrides=overrides
        )

        # Verify that the override was stored (even though it's faulty)
        assert (
            orchestrator.overrides.get_full_plan_prompt == faulty_get_full_plan_prompt
        )

        # The error should occur when the function is called
        with pytest.raises(ValueError, match="Custom prompt error"):
            orchestrator.overrides.get_full_plan_prompt("test", None, [])
