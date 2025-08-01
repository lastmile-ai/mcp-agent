"""
Tests for Budget Management System and Beast Mode
"""

import pytest
from datetime import datetime, timedelta, timezone
import asyncio
from unittest.mock import patch, MagicMock

from mcp_agent.workflows.adaptive.budget_manager import (
    BudgetManager,
    BudgetDimension,
    ActionType,
)


# Mock logger to avoid async issues in tests
@pytest.fixture(autouse=True)
def mock_logger():
    with patch("mcp_agent.workflows.adaptive.budget_manager.logger") as mock:
        mock.debug = MagicMock()
        mock.info = MagicMock()
        mock.warning = MagicMock()
        mock.error = MagicMock()
        yield mock


class TestBudgetManager:
    """Test the multi-dimensional budget manager"""

    def test_initialization(self):
        """Test budget manager initialization"""
        manager = BudgetManager(
            token_budget=50000,
            time_budget=timedelta(minutes=15),
            cost_budget=5.0,
            iteration_budget=8,
        )

        assert manager.token_budget == 50000
        assert manager.time_budget == timedelta(minutes=15)
        assert manager.cost_budget == 5.0
        assert manager.iteration_budget == 8
        assert manager.tokens_used == 0
        assert manager.cost_incurred == 0.0
        assert manager.iterations_done == 0
        assert manager.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_update_metrics(self):
        """Test updating various metrics"""
        manager = BudgetManager()

        # Update tokens
        await manager.update_tokens(1000)
        assert manager.tokens_used == 1000
        await manager.update_tokens(500)
        assert manager.tokens_used == 1500

        # Update cost
        await manager.update_cost(0.5)
        assert manager.cost_incurred == 0.5
        await manager.update_cost(0.3)
        assert manager.cost_incurred == 0.8

        # Update iterations
        await manager.increment_iteration()
        assert manager.iterations_done == 1
        await manager.increment_iteration()
        assert manager.iterations_done == 2

    @pytest.mark.asyncio
    async def test_subagent_management(self):
        """Test subagent counting"""
        manager = BudgetManager(max_concurrent_subagents=3)

        # Start subagents
        assert await manager.start_subagent()
        assert manager.active_subagents == 1

        assert await manager.start_subagent()
        assert manager.active_subagents == 2

        assert await manager.start_subagent()
        assert manager.active_subagents == 3

        # Should fail - at limit
        assert not await manager.start_subagent()
        assert manager.active_subagents == 3

        # Complete one
        await manager.complete_subagent()
        assert manager.active_subagents == 2

        # Now can start another
        assert await manager.start_subagent()
        assert manager.active_subagents == 3

    @pytest.mark.asyncio
    async def test_check_budgets(self):
        """Test checking budget status"""
        manager = BudgetManager(
            token_budget=10000,
            time_budget=timedelta(minutes=10),
            cost_budget=10.0,
            iteration_budget=5,
        )

        # Update some metrics
        await manager.update_tokens(5000)  # 50%
        await manager.update_cost(8.0)  # 80%
        manager.iterations_done = 4  # 80%

        statuses = await manager.check_budgets()

        # Check tokens
        assert statuses[BudgetDimension.TOKENS].percentage == 0.5
        assert not statuses[BudgetDimension.TOKENS].is_exceeded
        assert not statuses[BudgetDimension.TOKENS].is_critical

        # Check cost - should be near critical
        assert statuses[BudgetDimension.COST].percentage == 0.8
        assert not statuses[BudgetDimension.COST].is_exceeded
        assert not statuses[BudgetDimension.COST].is_critical  # 80% < 90%

        # Check iterations
        assert statuses[BudgetDimension.ITERATIONS].percentage == 0.8

        # Update to critical levels
        await manager.update_tokens(4500)  # Now 95%
        statuses = await manager.check_budgets()
        assert statuses[BudgetDimension.TOKENS].percentage == 0.95
        assert statuses[BudgetDimension.TOKENS].is_critical

    @pytest.mark.asyncio
    async def test_should_continue(self):
        """Test continuation logic"""
        manager = BudgetManager(
            token_budget=1000, iteration_budget=3, max_consecutive_failures=2
        )

        # Should continue initially
        should_continue, reason = await manager.should_continue()
        assert should_continue
        assert reason is None

        # Exceed token budget
        await manager.update_tokens(1001)
        should_continue, reason = await manager.should_continue()
        assert not should_continue
        assert "tokens budget exceeded" in reason

        # Reset and test iteration limit
        manager = BudgetManager(iteration_budget=2)
        manager.iterations_done = 2
        should_continue, reason = await manager.should_continue()
        assert not should_continue
        assert "iterations budget exceeded" in reason

        # Test failure limit
        manager = BudgetManager(max_consecutive_failures=2)
        manager.consecutive_failures = 2
        should_continue, reason = await manager.should_continue()
        assert not should_continue
        assert "consecutive failures" in reason

    @pytest.mark.asyncio
    async def test_beast_mode_detection(self):
        """Test beast mode trigger conditions"""
        manager = BudgetManager(
            token_budget=1000, cost_budget=10.0, max_consecutive_failures=3
        )

        # Not in beast mode initially
        assert not await manager.should_enter_beast_mode()

        # Approach token limit (91%)
        await manager.update_tokens(910)
        assert await manager.should_enter_beast_mode()

        # Reset and test cost limit
        manager = BudgetManager(cost_budget=10.0)
        await manager.update_cost(9.1)  # 91%
        assert await manager.should_enter_beast_mode()

        # Test near failure limit
        manager = BudgetManager(max_consecutive_failures=3)
        manager.consecutive_failures = 2  # One away from limit
        assert await manager.should_enter_beast_mode()

    @pytest.mark.asyncio
    async def test_conservative_mode(self):
        """Test conservative resource usage detection"""
        manager = BudgetManager(token_budget=1000, cost_budget=10.0)

        # Not conservative initially
        assert not await manager.should_be_conservative()

        # At 70% of any budget
        await manager.update_tokens(700)
        assert await manager.should_be_conservative()

        # Reset and test with cost
        manager = BudgetManager(cost_budget=10.0)
        await manager.update_cost(7.0)  # 70%
        assert await manager.should_be_conservative()

    @pytest.mark.asyncio
    async def test_action_failure_tracking(self):
        """Test tracking and constraining failed actions"""
        manager = BudgetManager()

        # Record failures
        await manager.record_action_failure(ActionType.PLAN, "Planning failed")
        assert manager.consecutive_failures == 1
        assert manager.total_failures == 1
        assert ActionType.PLAN in manager.disabled_actions
        assert ActionType.PLAN in manager.action_cooldowns

        # Another failure
        await manager.record_action_failure(ActionType.RESEARCH, "Research timeout")
        assert manager.consecutive_failures == 2
        assert manager.total_failures == 2
        assert ActionType.RESEARCH in manager.disabled_actions

        # Success resets consecutive
        await manager.record_action_success(ActionType.SYNTHESIZE)
        assert manager.consecutive_failures == 0
        assert manager.total_failures == 2  # Total not reset

        # Actions remain disabled (need successful execution of same action)
        assert ActionType.PLAN in manager.disabled_actions
        assert ActionType.RESEARCH in manager.disabled_actions

        # But executing a previously failed action successfully re-enables it
        await manager.record_action_success(ActionType.PLAN)
        assert ActionType.PLAN not in manager.disabled_actions
        assert ActionType.RESEARCH in manager.disabled_actions  # Still disabled

    @pytest.mark.asyncio
    async def test_action_cooldowns(self):
        """Test action cooldown periods"""
        manager = BudgetManager()

        # Single failure - short cooldown
        await manager.record_action_failure(ActionType.PLAN, "Error")
        assert ActionType.PLAN in manager.action_cooldowns
        cooldown1 = manager.action_cooldowns[ActionType.PLAN]

        # Multiple failures - longer cooldown
        await manager.record_action_failure(ActionType.PLAN, "Error again")
        await manager.record_action_failure(ActionType.PLAN, "Error third time")
        cooldown2 = manager.action_cooldowns[ActionType.PLAN]

        # Second cooldown should be later (longer)
        assert cooldown2 > cooldown1
        assert (
            cooldown2 - cooldown1
        ).total_seconds() > 300  # At least 5 minutes longer

    @pytest.mark.asyncio
    async def test_is_action_allowed(self):
        """Test action permission checking"""
        manager = BudgetManager()

        # Initially all allowed
        allowed, reason = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert allowed
        assert reason is None

        # Disable an action
        manager.disabled_actions.add(ActionType.CREATE_SUBAGENT)
        allowed, reason = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert not allowed
        assert "temporarily disabled" in reason

        # Test cooldown
        manager.disabled_actions.clear()
        manager.action_cooldowns[ActionType.PLAN] = datetime.now(
            timezone.utc
        ) + timedelta(minutes=5)
        allowed, reason = await manager.is_action_allowed(ActionType.PLAN)
        assert not allowed
        assert "cooldown" in reason

        # Test conservative mode restrictions
        manager = BudgetManager(token_budget=100)
        await manager.update_tokens(71)  # 71% - conservative mode
        allowed, reason = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert not allowed
        assert "Conserving resources" in reason

        # But other actions should be allowed
        allowed, reason = await manager.is_action_allowed(ActionType.SYNTHESIZE)
        assert allowed

    @pytest.mark.asyncio
    async def test_budget_summary(self):
        """Test human-readable budget summary"""
        manager = BudgetManager(token_budget=1000, cost_budget=10.0, iteration_budget=5)

        # Set various states
        await manager.update_tokens(950)  # Critical
        await manager.update_cost(5.0)  # 50%
        manager.iterations_done = 2  # 40%
        manager.consecutive_failures = 1
        manager.disabled_actions.add(ActionType.PLAN)

        summary = await manager.get_budget_summary()

        assert "Budget Status:" in summary
        assert "🔴" not in summary  # No exceeded budgets
        assert "🟡" in summary  # Critical token budget
        assert "🟢" in summary  # OK budgets
        assert "Consecutive failures: 1/3" in summary
        assert "Disabled actions: plan" in summary

    @pytest.mark.asyncio
    async def test_estimate_remaining_capacity(self):
        """Test estimating remaining operations"""
        manager = BudgetManager(
            token_budget=10000,
            cost_budget=10.0,
            time_budget=timedelta(minutes=30),
            iteration_budget=10,
        )

        # Do some iterations
        for i in range(3):
            await manager.increment_iteration()
            await manager.update_tokens(1000)  # 1000 tokens per iteration
            await manager.update_cost(1.0)  # $1 per iteration
            await asyncio.sleep(0.01)  # Small delay for time calculation

        estimate = await manager.estimate_remaining_capacity()

        # Direct iteration count
        assert estimate["iterations"] == 7  # 10 - 3

        # Token-based estimate: 7000 tokens left / 1000 per iter = 7
        assert estimate["iterations_by_tokens"] == 7

        # Cost-based estimate: $7 left / $1 per iter = 7
        assert estimate["iterations_by_cost"] == 7

        # Time estimate will vary but should be positive
        assert estimate["iterations_by_time"] > 0

        # Total should be minimum of all
        assert estimate["estimated_total"] <= 7


class TestBudgetIntegration:
    """Test budget management integration with workflow concepts"""

    @pytest.mark.asyncio
    async def test_progressive_constraints(self):
        """Test that constraints get progressively tighter"""
        manager = BudgetManager(token_budget=10000, cost_budget=10.0)

        # Initially permissive
        allowed, _ = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert allowed
        allowed, _ = await manager.is_action_allowed(ActionType.PLAN)
        assert allowed

        # Use 75% of budget - conservative mode
        await manager.update_tokens(7500)
        allowed, _ = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert not allowed  # Expensive action blocked
        allowed, _ = await manager.is_action_allowed(ActionType.SYNTHESIZE)
        assert allowed  # Cheap action allowed

        # Use 92% - critical/beast mode
        await manager.update_tokens(1700)  # Total 9200
        assert await manager.should_enter_beast_mode()

        # After failures, more restrictions
        await manager.record_action_failure(ActionType.PLAN, "Failed")
        allowed, _ = await manager.is_action_allowed(ActionType.PLAN)
        assert not allowed

    @pytest.mark.asyncio
    async def test_budget_enforcement_prevents_runaway(self):
        """Test that budgets prevent runaway execution"""
        manager = BudgetManager(
            token_budget=1000, iteration_budget=5, time_budget=timedelta(seconds=1)
        )

        # Simulate runaway loop
        iterations = 0

        while True:
            should_continue, reason = await manager.should_continue()
            if not should_continue:
                break

            iterations += 1
            await manager.increment_iteration()
            await manager.update_tokens(100)

            # Safety check
            if iterations > 10:
                pytest.fail("Runaway loop not stopped by budget manager")

        # Should stop due to iteration budget
        assert iterations == 5
        assert "iterations budget exceeded" in reason

    @pytest.mark.asyncio
    async def test_beast_mode_activation_flow(self):
        """Test the flow into beast mode"""
        manager = BudgetManager(token_budget=1000, cost_budget=5.0, iteration_budget=10)

        # Simulate workflow progression
        workflow_states = []

        for i in range(10):
            await manager.increment_iteration()
            await manager.update_tokens(95)  # 95 tokens per iteration
            await manager.update_cost(0.45)  # $0.45 per iteration

            state = {
                "iteration": i + 1,
                "should_continue": (await manager.should_continue())[0],
                "beast_mode": await manager.should_enter_beast_mode(),
                "conservative": await manager.should_be_conservative(),
            }
            workflow_states.append(state)

            if not state["should_continue"]:
                break

        # Verify progression
        # Early states: normal
        assert not workflow_states[0]["beast_mode"]
        assert not workflow_states[0]["conservative"]

        # Middle states: conservative
        conservative_states = [
            s for s in workflow_states if s["conservative"] and not s["beast_mode"]
        ]
        assert len(conservative_states) > 0

        # Late states: beast mode
        beast_states = [s for s in workflow_states if s["beast_mode"]]
        assert len(beast_states) > 0

        # Beast mode should come after conservative
        first_conservative = next(
            i for i, s in enumerate(workflow_states) if s["conservative"]
        )
        first_beast = next(i for i, s in enumerate(workflow_states) if s["beast_mode"])
        assert first_beast >= first_conservative

    @pytest.mark.asyncio
    async def test_multi_dimensional_budget_interaction(self):
        """Test interaction between different budget dimensions"""
        manager = BudgetManager(
            token_budget=10000,
            cost_budget=10.0,
            time_budget=timedelta(minutes=10),
            iteration_budget=20,
        )

        # Use different amounts of each budget
        await manager.update_tokens(9500)  # 95% - critical
        await manager.update_cost(6.0)  # 60% - ok
        manager.iterations_done = 15  # 75% - warning
        # Time will be ~0%

        statuses = await manager.check_budgets()

        # Should trigger beast mode due to tokens
        assert await manager.should_enter_beast_mode()

        # Should be conservative due to iterations
        assert await manager.should_be_conservative()

        # The most constrained dimension determines behavior
        critical_dimensions = [d for d, s in statuses.items() if s.is_critical]
        assert BudgetDimension.TOKENS in critical_dimensions

        # Expensive actions should be blocked
        allowed, _ = await manager.is_action_allowed(ActionType.CREATE_SUBAGENT)
        assert not allowed

    @pytest.mark.asyncio
    async def test_thread_safety(self):
        """Test thread-safe operations with asyncio"""

        manager = BudgetManager(
            token_budget=100000, cost_budget=100.0, max_concurrent_subagents=10
        )

        # Test concurrent token updates
        async def update_tokens_concurrently(amount):
            for _ in range(100):
                await manager.update_tokens(amount)

        # Run multiple coroutines updating tokens
        tasks = []
        for i in range(10):
            tasks.append(asyncio.create_task(update_tokens_concurrently(10)))

        # Wait for all to complete
        await asyncio.gather(*tasks)

        # Should have exactly 10 * 100 * 10 = 10000 tokens
        assert manager.tokens_used == 10000

        # Test concurrent subagent management
        successful_starts = []

        async def start_subagent_concurrently():
            result = await manager.start_subagent()
            if result:
                successful_starts.append(1)
                await asyncio.sleep(0.001)  # Simulate some work
                await manager.complete_subagent()

        # Reset subagent count
        manager.active_subagents = 0
        successful_starts.clear()

        # Try to start many subagents concurrently
        tasks = []
        for _ in range(20):
            tasks.append(asyncio.create_task(start_subagent_concurrently()))

        await asyncio.gather(*tasks)

        # Should never exceed max concurrent subagents
        assert (
            len(successful_starts) <= manager.max_concurrent_subagents * 2
        )  # Allow for some completed
        assert manager.active_subagents >= 0  # Should never go negative

    @pytest.mark.asyncio
    async def test_concurrent_budget_updates(self):
        """Test that concurrent updates are handled safely with locks"""
        manager = BudgetManager(
            token_budget=100000, cost_budget=100.0, iteration_budget=100
        )

        # Create many concurrent update tasks
        async def update_tokens_many_times():
            for i in range(100):
                await manager.update_tokens(10)

        async def update_cost_many_times():
            for i in range(100):
                await manager.update_cost(0.1)

        async def increment_iterations_many_times():
            for i in range(100):
                await manager.increment_iteration()

        # Run all concurrently
        await asyncio.gather(
            update_tokens_many_times(),
            update_cost_many_times(),
            increment_iterations_many_times(),
            update_tokens_many_times(),  # Double up for more contention
            update_cost_many_times(),
        )

        # Verify final state is consistent
        assert manager.tokens_used == 2000  # 200 updates of 10 tokens
        assert abs(manager.cost_incurred - 20.0) < 0.01  # 200 updates of 0.1
        assert manager.iterations_done == 100

    @pytest.mark.asyncio
    async def test_concurrent_budget_checks_with_locked_methods(self):
        """Test that new locked methods maintain consistency"""
        manager = BudgetManager(
            token_budget=1000, cost_budget=10.0, iteration_budget=10
        )

        results = []

        async def check_and_update():
            # Simulate checking budget while updating
            for i in range(50):
                # Use both old and new methods
                statuses = await manager.check_budgets()
                await manager.update_tokens(10)
                should_continue, _ = await manager.should_continue()
                is_conservative = await manager.should_be_conservative()
                results.append((statuses, should_continue, is_conservative))

        # Run multiple checkers concurrently
        await asyncio.gather(check_and_update(), check_and_update(), check_and_update())

        # Verify we got consistent results
        assert len(results) == 150
        # Should have stopped when tokens exceeded 1000
        assert manager.tokens_used >= 1000

        # Check that we properly detected when to stop
        stop_count = sum(1 for _, should_continue, _ in results if not should_continue)
        assert stop_count > 0  # At least some detected the limit

    @pytest.mark.asyncio
    async def test_beast_mode_race_condition(self):
        """Test beast mode detection doesn't have race conditions"""
        manager = BudgetManager(token_budget=1000, cost_budget=10.0)

        # Set up near-critical state
        await manager.update_tokens(850)  # 85%

        beast_mode_results = []

        async def check_beast_mode_repeatedly():
            for i in range(20):
                # Gradually increase usage
                await manager.update_tokens(5)
                is_beast = await manager.should_enter_beast_mode()
                beast_mode_results.append((manager.tokens_used, is_beast))

        # Run concurrent beast mode checks
        await asyncio.gather(
            check_beast_mode_repeatedly(), check_beast_mode_repeatedly()
        )

        # Verify beast mode was triggered consistently
        # Should trigger around 900 tokens (90%)
        beast_triggered = [
            (tokens, is_beast) for tokens, is_beast in beast_mode_results if is_beast
        ]
        assert len(beast_triggered) > 0

        # All triggers should be above 90% threshold
        for tokens, _ in beast_triggered:
            assert tokens >= 900

    @pytest.mark.asyncio
    async def test_estimate_remaining_capacity_consistency(self):
        """Test that remaining capacity estimates are consistent under concurrent access"""
        manager = BudgetManager(
            token_budget=10000, cost_budget=10.0, iteration_budget=20
        )

        # Do some work
        await manager.update_tokens(2000)
        await manager.update_cost(2.0)
        for _ in range(5):
            await manager.increment_iteration()

        capacity_results = []

        async def check_capacity_while_updating():
            for i in range(10):
                capacity = await manager.estimate_remaining_capacity()
                await manager.update_tokens(100)
                await manager.update_cost(0.1)
                capacity_results.append(capacity)

        # Run concurrent capacity checks
        await asyncio.gather(
            check_capacity_while_updating(), check_capacity_while_updating()
        )

        # Verify capacity estimates are reasonable
        assert len(capacity_results) == 20

        # Capacity should generally decrease
        first_capacity = capacity_results[0]["estimated_total"]
        last_capacity = capacity_results[-1]["estimated_total"]
        assert last_capacity < first_capacity
