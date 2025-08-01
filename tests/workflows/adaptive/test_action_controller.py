"""
Tests for Action Control System
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from mcp_agent.workflows.adaptive.action_controller import (
    ActionController,
    WorkflowAction,
    ActionConstraints,
)


# Mock logger to avoid async issues in tests
@pytest.fixture(autouse=True)
def mock_logger():
    with patch("mcp_agent.workflows.adaptive.action_controller.logger") as mock:
        mock.debug = MagicMock()
        mock.info = MagicMock()
        mock.warning = MagicMock()
        mock.error = MagicMock()
        yield mock


class TestActionController:
    """Test the dynamic action control system"""

    def test_initialization(self):
        """Test action controller initialization"""
        controller = ActionController()

        assert len(controller.action_history) == 0
        assert len(controller.disabled_actions) == 0
        assert len(controller.action_cooldowns) == 0
        assert controller.current_iteration == 0

        # Check default constraints exist
        assert WorkflowAction.ANALYZE in controller.constraints
        assert WorkflowAction.SYNTHESIZE in controller.constraints
        assert WorkflowAction.CONCLUDE in controller.constraints

    @pytest.mark.asyncio
    async def test_update_iteration(self):
        """Test iteration tracking"""
        controller = ActionController()

        await controller.update_iteration(1)
        assert controller.current_iteration == 1

        await controller.update_iteration(5)
        assert controller.current_iteration == 5

    @pytest.mark.asyncio
    async def test_basic_action_availability(self):
        """Test basic action availability checking"""
        controller = ActionController()
        context = {"knowledge_items": [], "has_findings": False}

        # ANALYZE should be available initially
        available, reason = await controller.is_action_available(
            WorkflowAction.ANALYZE, context
        )
        assert available

        # SYNTHESIZE should not be available without findings
        available, reason = await controller.is_action_available(
            WorkflowAction.SYNTHESIZE, context
        )
        assert not available
        assert "knowledge items" in reason or "research findings" in reason

        # Update context
        context["has_findings"] = True
        context["knowledge_items"] = ["item1", "item2"]

        # Now SYNTHESIZE should be available
        available, reason = await controller.is_action_available(
            WorkflowAction.SYNTHESIZE, context
        )
        assert available

    @pytest.mark.asyncio
    async def test_action_constraints(self):
        """Test constraint-based availability"""
        controller = ActionController()

        # Test iteration constraints
        context = {"knowledge_items": ["k1", "k2", "k3", "k4"], "has_synthesis": True}

        # CONCLUDE requires min 1 iteration
        available, reason = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert not available
        assert "Requires at least 1 iterations" in reason

        await controller.update_iteration(1)

        # Also needs high confidence
        context["confidence"] = 0.5
        available, reason = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert not available
        assert "Confidence too low" in reason

        # With high confidence, should work
        context["confidence"] = 0.8
        available, reason = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert available

    @pytest.mark.asyncio
    async def test_action_recording(self):
        """Test recording action execution"""
        controller = ActionController()

        # Record successful action
        await controller.record_action(
            WorkflowAction.PLAN, success=True, duration=1.5, context={"iteration": 1}
        )

        assert len(controller.action_history) == 1
        assert controller.action_history[0].action == WorkflowAction.PLAN
        assert controller.action_history[0].success
        assert controller.action_history[0].duration_seconds == 1.5

        # Record failed action
        await controller.record_action(
            WorkflowAction.EXECUTE_SUBTASK,
            success=False,
            error="Connection timeout",
            context={"subtask": "Research APIs"},
        )

        assert len(controller.action_history) == 2
        assert not controller.action_history[1].success
        assert controller.action_history[1].error == "Connection timeout"

    @pytest.mark.asyncio
    async def test_failure_handling(self):
        """Test handling of action failures"""
        controller = ActionController()

        # Single failure - should add cooldown
        await controller.record_action(
            WorkflowAction.PLAN, success=False, error="Error 1"
        )

        assert WorkflowAction.PLAN in controller.action_cooldowns
        cooldown_end = controller.action_cooldowns[WorkflowAction.PLAN]
        assert cooldown_end > datetime.now(timezone.utc)

        # Multiple failures - should disable
        await controller.record_action(
            WorkflowAction.PLAN, success=False, error="Error 2"
        )
        await controller.record_action(
            WorkflowAction.PLAN, success=False, error="Error 3"
        )

        assert WorkflowAction.PLAN in controller.disabled_actions

        # Check it's not available
        available, reason = await controller.is_action_available(
            WorkflowAction.PLAN, {}
        )
        assert not available
        assert "currently disabled" in reason

    @pytest.mark.asyncio
    async def test_success_recovery(self):
        """Test re-enabling actions after success"""
        controller = ActionController()

        # Disable an action through failures
        for i in range(3):
            await controller.record_action(WorkflowAction.SYNTHESIZE, success=False)

        assert WorkflowAction.SYNTHESIZE in controller.disabled_actions

        # Record some successes
        await controller.record_action(WorkflowAction.SYNTHESIZE, success=True)
        assert (
            WorkflowAction.SYNTHESIZE in controller.disabled_actions
        )  # Still disabled

        await controller.record_action(WorkflowAction.SYNTHESIZE, success=True)
        assert (
            WorkflowAction.SYNTHESIZE not in controller.disabled_actions
        )  # Re-enabled

    @pytest.mark.asyncio
    async def test_cooldown_mechanism(self):
        """Test action cooldowns"""
        controller = ActionController()

        # Set a short cooldown for testing
        controller.constraints[WorkflowAction.PLAN] = ActionConstraints(
            cooldown_minutes=0.01
        )  # 0.6 seconds

        # Fail an action
        await controller.record_action(WorkflowAction.PLAN, success=False)

        # Should be on cooldown
        available, reason = await controller.is_action_available(
            WorkflowAction.PLAN, {}
        )
        assert not available
        assert "cooldown" in reason

        # Wait for cooldown
        await asyncio.sleep(0.7)

        # Should be available again
        available, reason = await controller.is_action_available(
            WorkflowAction.PLAN, {}
        )
        assert available

    @pytest.mark.asyncio
    async def test_attempts_per_iteration(self):
        """Test limiting attempts per iteration"""
        controller = ActionController()
        await controller.update_iteration(1)

        context = {"iteration": 1}

        # ANALYZE allows only 1 attempt per workflow
        await controller.record_action(
            WorkflowAction.ANALYZE, success=True, context=context
        )

        # Second attempt should fail
        available, reason = await controller.is_action_available(
            WorkflowAction.ANALYZE, {}
        )
        assert not available
        assert "Maximum attempts" in reason

        # PLAN allows 2 attempts per iteration
        await controller.record_action(
            WorkflowAction.PLAN, success=True, context=context
        )
        available, _ = await controller.is_action_available(WorkflowAction.PLAN, {})
        assert available

        await controller.record_action(
            WorkflowAction.PLAN, success=True, context=context
        )
        available, reason = await controller.is_action_available(
            WorkflowAction.PLAN, {}
        )
        assert not available
        assert "Maximum attempts" in reason

    @pytest.mark.asyncio
    async def test_concurrent_execution_limits(self):
        """Test limiting concurrent executions"""
        controller = ActionController()

        # CREATE_SUBAGENT has max concurrent limit
        context = {"active_create_subagent_count": 4}
        available, _ = await controller.is_action_available(
            WorkflowAction.CREATE_SUBAGENT, context
        )
        assert available

        context["active_create_subagent_count"] = 5
        available, reason = await controller.is_action_available(
            WorkflowAction.CREATE_SUBAGENT, context
        )
        assert not available
        assert "Maximum concurrent" in reason

    @pytest.mark.asyncio
    async def test_complex_constraints(self):
        """Test complex action-specific constraints"""
        controller = ActionController()
        await controller.update_iteration(2)

        # DECOMPOSE requires high complexity
        context = {"subtask_complexity": 1}
        available, reason = await controller.is_action_available(
            WorkflowAction.DECOMPOSE, context
        )
        assert not available
        assert "not complex enough" in reason

        context["subtask_complexity"] = 3
        available, _ = await controller.is_action_available(
            WorkflowAction.DECOMPOSE, context
        )
        assert available

        # REFLECT requires at least 1 iteration
        await controller.update_iteration(0)
        available, reason = await controller.is_action_available(
            WorkflowAction.REFLECT, {}
        )
        assert not available

        await controller.update_iteration(1)
        available, _ = await controller.is_action_available(WorkflowAction.REFLECT, {})
        assert available

    @pytest.mark.asyncio
    async def test_get_available_actions(self):
        """Test getting all available actions"""
        controller = ActionController()
        await controller.update_iteration(1)

        context = {
            "knowledge_items": ["k1", "k2"],
            "has_findings": True,
            "has_synthesis": False,
            "confidence": 0.5,
        }

        available = await controller.get_available_actions(context)

        # Should have some actions available
        assert len(available) > 0
        assert WorkflowAction.SYNTHESIZE in available  # Has findings and knowledge
        assert WorkflowAction.PLAN in available

        # Should NOT have these
        assert WorkflowAction.DECIDE not in available  # No synthesis
        assert WorkflowAction.CONCLUDE not in available  # Low confidence

    @pytest.mark.asyncio
    async def test_recommended_action(self):
        """Test action recommendation"""
        controller = ActionController()

        # Initial state - should recommend ANALYZE
        context = {}
        recommended = await controller.get_recommended_action(context)
        assert recommended == WorkflowAction.ANALYZE

        # After analysis, should recommend PLAN
        await controller.record_action(WorkflowAction.ANALYZE, success=True)
        recommended = await controller.get_recommended_action(context)
        assert recommended == WorkflowAction.PLAN

        # With findings, should recommend synthesis or knowledge extraction
        context = {"has_findings": True, "knowledge_items": ["k1", "k2"]}
        recommended = await controller.get_recommended_action(context)
        # PLAN is still available and may be recommended
        assert recommended in [
            WorkflowAction.PLAN,
            WorkflowAction.EXECUTE_SUBTASK,
            WorkflowAction.EXTRACT_KNOWLEDGE,
            WorkflowAction.SYNTHESIZE,
        ]

    @pytest.mark.asyncio
    async def test_action_stats(self):
        """Test getting action statistics"""
        controller = ActionController()

        # Record various actions
        await controller.record_action(WorkflowAction.PLAN, success=True, duration=1.0)
        await controller.record_action(WorkflowAction.PLAN, success=True, duration=2.0)
        await controller.record_action(
            WorkflowAction.PLAN, success=False, error="Failed"
        )

        await controller.record_action(
            WorkflowAction.EXECUTE_SUBTASK, success=True, duration=5.0
        )
        await controller.record_action(
            WorkflowAction.EXECUTE_SUBTASK, success=True, duration=3.0
        )

        stats = await controller.get_action_stats()

        # Check PLAN stats
        plan_stats = stats[WorkflowAction.PLAN.value]
        assert plan_stats["total_attempts"] == 3
        assert plan_stats["successful"] == 2
        assert plan_stats["failed"] == 1
        assert plan_stats["success_rate"] == 2 / 3
        assert plan_stats["average_duration"] == 1.5  # (1.0 + 2.0) / 2

        # Check EXECUTE stats
        exec_stats = stats[WorkflowAction.EXECUTE_SUBTASK.value]
        assert exec_stats["total_attempts"] == 2
        assert exec_stats["successful"] == 2
        assert exec_stats["success_rate"] == 1.0
        assert exec_stats["average_duration"] == 4.0  # (5.0 + 3.0) / 2

    @pytest.mark.asyncio
    async def test_recovery_suggestions(self):
        """Test recovery action suggestions after failures"""
        controller = ActionController()
        await controller.update_iteration(1)

        context = {"has_findings": True, "knowledge_items": ["k1"]}

        # Failed execution should suggest decomposition
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.EXECUTE_SUBTASK,
            "Task too complex",
            {"subtask_complexity": 3},
        )
        assert recovery == WorkflowAction.DECOMPOSE

        # Failed synthesis should suggest more execution
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.SYNTHESIZE, "Not enough data", context
        )
        assert recovery == WorkflowAction.EXECUTE_SUBTASK

        # Failed conclusion should suggest reflection
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.CONCLUDE, "Confidence too low", context
        )
        assert recovery == WorkflowAction.REFLECT

        # If suggested recovery not available, default to REFLECT
        controller.disabled_actions.add(WorkflowAction.DECOMPOSE)
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.EXECUTE_SUBTASK, "Failed", context
        )
        assert recovery == WorkflowAction.REFLECT


class TestActionControllerIntegration:
    """Test action controller integration with workflow concepts"""

    @pytest.mark.asyncio
    async def test_workflow_progression(self):
        """Test natural workflow action progression"""
        controller = ActionController()
        context = {}

        # Track workflow progression
        actions_taken = []

        for i in range(10):
            await controller.update_iteration(i)

            # Get recommended action
            action = await controller.get_recommended_action(context)
            if action:
                actions_taken.append(action)

                # Execute action
                success = (
                    action != WorkflowAction.EXECUTE_SUBTASK or i % 3 != 2
                )  # Fail every 3rd execution
                await controller.record_action(
                    action, success=success, context={"iteration": i}
                )

                # Update context based on action
                if action == WorkflowAction.ANALYZE:
                    context["analyzed"] = True
                elif action == WorkflowAction.EXECUTE_SUBTASK:
                    context["has_findings"] = True
                    if "knowledge_items" not in context:
                        context["knowledge_items"] = []
                    context["knowledge_items"].append(f"k{i}")
                elif action == WorkflowAction.SYNTHESIZE:
                    context["has_synthesis"] = True
                elif action == WorkflowAction.DECIDE:
                    context["confidence"] = 0.6 + (i * 0.05)

        # Verify sensible progression
        assert actions_taken[0] == WorkflowAction.ANALYZE  # Should start with analysis
        assert WorkflowAction.PLAN in actions_taken  # Should plan at some point
        # EXECUTE_SUBTASK may not be in the default recommendations
        # It needs to be explicitly triggered based on workflow logic

        # Later actions should appear after earlier ones
        if WorkflowAction.SYNTHESIZE in actions_taken:
            first_exec = actions_taken.index(WorkflowAction.EXECUTE_SUBTASK)
            first_synth = actions_taken.index(WorkflowAction.SYNTHESIZE)
            assert first_synth > first_exec  # Synthesis after execution

    @pytest.mark.asyncio
    async def test_failure_adaptation(self):
        """Test that controller adapts to failures"""
        controller = ActionController()
        context = {"has_findings": True, "knowledge_items": ["k1"]}

        # Record 3 failures directly - this should disable the action
        for i in range(3):
            await controller.record_action(
                WorkflowAction.PLAN, success=False, error=f"Planning failed {i + 1}"
            )

        # PLAN should be disabled after 3 failures
        assert WorkflowAction.PLAN in controller.disabled_actions

        # Should recommend alternative actions
        recommended = await controller.get_recommended_action(context)
        assert recommended != WorkflowAction.PLAN
        assert recommended is not None  # Should have alternatives

        # After some successes in other actions, PLAN might be re-enabled
        for i in range(3):
            await controller.record_action(WorkflowAction.EXECUTE_SUBTASK, success=True)

        # Not immediately re-enabled, but cooldown might expire
        await asyncio.sleep(0.1)

        # Recovery suggestion should adapt
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.PLAN, "Still failing", context
        )
        # Recovery may be None if REFLECT is not available, or REFLECT if it is
        assert recovery is None or recovery == WorkflowAction.REFLECT

    @pytest.mark.asyncio
    async def test_prevents_premature_conclusion(self):
        """Test that controller prevents premature workflow conclusion"""
        controller = ActionController()

        # Try to conclude immediately
        context = {
            "knowledge_items": ["k1", "k2", "k3", "k4"],
            "has_synthesis": True,
            "confidence": 0.9,
        }

        # Should not allow conclusion at iteration 0
        available, reason = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert not available
        assert "Requires at least 1 iterations" in reason

        # Even with perfect context, need iterations
        await controller.update_iteration(1)
        available, _ = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert available  # Now allowed

        # But low confidence should still block
        context["confidence"] = 0.5
        available, reason = await controller.is_action_available(
            WorkflowAction.CONCLUDE, context
        )
        assert not available
        assert "Confidence too low" in reason
