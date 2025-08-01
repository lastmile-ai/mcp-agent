"""
Async tests for Action Control System
Tests the async ActionController implementation with proper concurrency handling
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

from mcp_agent.workflows.adaptive.action_controller import (
    ActionController,
    WorkflowAction,
    ActionConstraints,
)


# Mock logger to avoid issues in tests
@pytest.fixture(autouse=True)
def mock_logger():
    with patch("mcp_agent.workflows.adaptive.action_controller.logger") as mock:
        mock.debug = MagicMock()
        mock.info = MagicMock()
        mock.warning = MagicMock()
        mock.error = MagicMock()
        yield mock


class TestAsyncActionController:
    """Test the async action control system with concurrency safety"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test action controller initialization with async lock"""
        controller = ActionController()

        # Lock should exist immediately after initialization
        assert controller._lock is not None
        assert isinstance(controller._lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_basic_action_availability(self):
        """Test basic async action availability checking"""
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
    async def test_concurrent_action_recording(self):
        """Test recording actions concurrently to verify lock safety"""
        controller = ActionController()

        # Record 100 actions concurrently
        tasks = []
        for i in range(100):
            success = i % 2 == 0
            task = controller.record_action(
                WorkflowAction.EXECUTE_SUBTASK,
                success=success,
                duration=0.1 * i,
                context={"iteration": i},
            )
            tasks.append(task)

        # Execute all concurrently
        await asyncio.gather(*tasks)

        # Verify all were recorded correctly
        assert len(controller.action_history) == 100

        # Check that successful and failed counts match
        successful_count = sum(1 for h in controller.action_history if h.success)
        failed_count = sum(1 for h in controller.action_history if not h.success)

        assert successful_count == 50
        assert failed_count == 50

    @pytest.mark.asyncio
    async def test_concurrent_availability_checks(self):
        """Test checking availability concurrently"""
        controller = ActionController()

        # Set up a context
        context = {
            "knowledge_items": ["k1", "k2"],
            "has_findings": True,
            "has_synthesis": True,
            "confidence": 0.8,
        }

        # Check all actions concurrently
        tasks = []
        for action in WorkflowAction:
            task = controller.is_action_available(action, context)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Should get consistent results
        assert len(results) == len(WorkflowAction)
        # All results should be tuples of (bool, str or None)
        for result in results:
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], bool)

    @pytest.mark.asyncio
    async def test_failure_handling_async(self):
        """Test async handling of action failures"""
        controller = ActionController()

        # Record multiple failures concurrently
        tasks = []
        for i in range(3):
            task = controller.record_action(
                WorkflowAction.PLAN, success=False, error=f"Error {i}"
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Should be disabled after 3 failures
        assert WorkflowAction.PLAN in controller.disabled_actions

        # Check it's not available
        available, reason = await controller.is_action_available(
            WorkflowAction.PLAN, {}
        )
        assert not available
        assert "currently disabled" in reason

    @pytest.mark.asyncio
    async def test_success_recovery_async(self):
        """Test async re-enabling actions after success"""
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
    async def test_cooldown_mechanism_async(self):
        """Test async action cooldowns"""
        controller = ActionController()

        # Set a short cooldown for testing
        controller.constraints[WorkflowAction.PLAN] = ActionConstraints(
            cooldown_minutes=0.01  # 0.6 seconds
        )

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
    async def test_get_available_actions_async(self):
        """Test async getting all available actions"""
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
    async def test_get_action_stats_async(self):
        """Test async action statistics with concurrent access"""
        controller = ActionController()

        # Record various actions
        await controller.record_action(WorkflowAction.PLAN, success=True, duration=1.5)
        await controller.record_action(
            WorkflowAction.PLAN, success=False, error="Test error"
        )
        await controller.record_action(
            WorkflowAction.EXECUTE_SUBTASK, success=True, duration=2.0
        )

        # Get stats while recording more actions concurrently
        stats_task = controller.get_action_stats()
        record_task = controller.record_action(
            WorkflowAction.SYNTHESIZE, success=True, duration=3.0
        )

        stats, _ = await asyncio.gather(stats_task, record_task)

        # Verify stats structure
        assert WorkflowAction.PLAN.value in stats
        plan_stats = stats[WorkflowAction.PLAN.value]
        assert plan_stats["total_attempts"] >= 2
        assert plan_stats["successful"] >= 1
        assert plan_stats["failed"] >= 1

    @pytest.mark.asyncio
    async def test_suggest_recovery_action_async(self):
        """Test async recovery action suggestions"""
        controller = ActionController()
        await controller.update_iteration(2)

        context = {
            "knowledge_items": ["k1", "k2"],
            "has_findings": True,
            "has_synthesis": True,
        }

        # Test various failure recoveries
        recovery = await controller.suggest_recovery_action(
            WorkflowAction.EXECUTE_SUBTASK, "Connection timeout", context
        )
        # Check if DECOMPOSE is available
        decompose_available, reason = await controller.is_action_available(
            WorkflowAction.DECOMPOSE, context
        )
        if not decompose_available:
            # If DECOMPOSE is not available, should fall back to REFLECT
            assert recovery == WorkflowAction.REFLECT
        else:
            assert recovery == WorkflowAction.DECOMPOSE  # Should suggest breaking down

        recovery = await controller.suggest_recovery_action(
            WorkflowAction.SYNTHESIZE, "Not enough data", context
        )
        assert (
            recovery == WorkflowAction.EXECUTE_SUBTASK
        )  # Should suggest more research

    @pytest.mark.asyncio
    async def test_race_condition_prevention(self):
        """Test that the async lock prevents race conditions"""
        controller = ActionController()

        # Create a situation where we might have race conditions
        # Multiple threads trying to disable the same action
        async def try_record_failures(action: WorkflowAction, count: int):
            for i in range(count):
                await controller.record_action(
                    action, success=False, error=f"Error {i}"
                )

        # Run multiple coroutines that might cause race conditions
        tasks = [
            try_record_failures(WorkflowAction.PLAN, 2),
            try_record_failures(WorkflowAction.PLAN, 2),
            try_record_failures(WorkflowAction.PLAN, 2),
        ]

        await asyncio.gather(*tasks)

        # Should have exactly 6 failures recorded
        plan_failures = [
            h
            for h in controller.action_history
            if h.action == WorkflowAction.PLAN and not h.success
        ]
        assert len(plan_failures) == 6

        # Action should be disabled (3+ failures)
        assert WorkflowAction.PLAN in controller.disabled_actions

    @pytest.mark.asyncio
    async def test_recommended_action_async(self):
        """Test async recommended action with complex state"""
        controller = ActionController()
        await controller.update_iteration(2)

        # Test priority ordering
        context = {
            "knowledge_items": ["k1", "k2", "k3"],
            "has_findings": True,
            "has_synthesis": True,
            "confidence": 0.8,
        }

        # Record ANALYZE as already done
        await controller.record_action(WorkflowAction.ANALYZE, success=True)

        recommended = await controller.get_recommended_action(context)

        # Should recommend something (not ANALYZE since it's done)
        assert recommended is not None
        assert recommended != WorkflowAction.ANALYZE
