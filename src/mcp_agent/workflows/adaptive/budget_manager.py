"""
Budget Management System for AdaptiveWorkflow
Implements progressive budget enforcement with multiple dimensions
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Set, Optional, Tuple
from enum import Enum
import asyncio

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class BudgetDimension(str, Enum):
    """Different dimensions of budget we track"""

    TOKENS = "tokens"
    TIME = "time"
    COST = "cost"
    ITERATIONS = "iterations"
    SUBAGENTS = "subagents"


class ActionType(str, Enum):
    """Types of actions that can be constrained"""

    PLAN = "plan"
    RESEARCH = "research"
    SYNTHESIZE = "synthesize"
    CONCLUDE = "conclude"
    CREATE_SUBAGENT = "create_subagent"
    REFLECT = "reflect"


@dataclass
class BudgetStatus:
    """Current status of a budget dimension"""

    dimension: BudgetDimension
    used: float
    limit: float
    percentage: float
    is_exceeded: bool
    is_critical: bool  # > 90% used

    def __repr__(self) -> str:
        return (
            f"{self.dimension.value}: {self.percentage:.1%} ({self.used}/{self.limit})"
        )


@dataclass
class BudgetManager:
    """Manages multiple budget dimensions with progressive enforcement"""

    # Budget limits
    token_budget: int = 100000
    time_budget: timedelta = timedelta(minutes=30)
    cost_budget: float = 10.0
    iteration_budget: int = 10
    max_concurrent_subagents: int = 5

    # Current usage
    tokens_used: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cost_incurred: float = 0.0
    iterations_done: int = 0
    active_subagents: int = 0

    # Failure tracking
    consecutive_failures: int = 0
    total_failures: int = 0
    failure_by_action: Dict[str, int] = field(default_factory=dict)
    max_consecutive_failures: int = 3

    # Action constraints
    disabled_actions: Set[ActionType] = field(default_factory=set)
    action_cooldowns: Dict[ActionType, datetime] = field(default_factory=dict)

    # Budget enforcement thresholds
    warning_threshold: float = 0.7  # 70% - start being conservative
    critical_threshold: float = 0.9  # 90% - prepare for completion

    # Configurable cooldown parameters
    short_cooldown_minutes: int = 2  # For occasional failures
    long_cooldown_minutes: int = 10  # For repeated failures
    failure_threshold_for_long_cooldown: int = (
        3  # Number of failures before long cooldown
    )
    max_failures_for_re_enable: int = (
        5  # Max failures before action can't be re-enabled
    )

    # Conservative mode restrictions
    conservative_restricted_actions: Set[ActionType] = field(
        default_factory=lambda: {ActionType.CREATE_SUBAGENT, ActionType.PLAN}
    )

    def __post_init__(self):
        """Initialize async lock after dataclass initialization"""
        self._lock = asyncio.Lock()

    async def update_tokens(self, tokens: int) -> None:
        """Update token usage"""
        async with self._lock:
            self.tokens_used += tokens
            logger.debug(f"Token usage: {self.tokens_used}/{self.token_budget}")

    async def update_cost(self, cost: float) -> None:
        """Update cost incurred"""
        async with self._lock:
            self.cost_incurred += cost
            logger.debug(
                f"Cost incurred: ${self.cost_incurred:.2f}/${self.cost_budget}"
            )

    async def set_absolute_usage(self, tokens: int, cost: float) -> None:
        """Set absolute token and cost usage (used when syncing with TokenCounter)"""
        async with self._lock:
            self.tokens_used = tokens
            self.cost_incurred = cost
            logger.debug(
                f"BudgetManager.set_absolute_usage called - Tokens: {self.tokens_used}/{self.token_budget}, Cost: ${self.cost_incurred:.2f}/${self.cost_budget}"
            )

    async def increment_iteration(self) -> None:
        """Increment iteration count"""
        async with self._lock:
            self.iterations_done += 1
            logger.debug(f"Iterations: {self.iterations_done}/{self.iteration_budget}")

    async def start_subagent(self) -> bool:
        """Try to start a new subagent. Returns True if allowed."""
        async with self._lock:
            if self.active_subagents >= self.max_concurrent_subagents:
                return False
            self.active_subagents += 1
            return True

    async def complete_subagent(self) -> None:
        """Mark a subagent as completed"""
        async with self._lock:
            self.active_subagents = max(0, self.active_subagents - 1)

    def get_time_elapsed(self) -> timedelta:
        """Get time elapsed since start"""
        return datetime.now(timezone.utc) - self.start_time

    async def check_budgets(self) -> Dict[BudgetDimension, BudgetStatus]:
        """Check all budgets and return status for each dimension"""
        async with self._lock:
            return await self.check_budgets_locked()

    async def check_budgets_locked(self) -> Dict[BudgetDimension, BudgetStatus]:
        """Internal helper that assumes lock is already held"""
        time_elapsed = self.get_time_elapsed()

        statuses = {}

        # Token budget
        token_pct = self.tokens_used / self.token_budget if self.token_budget > 0 else 0
        statuses[BudgetDimension.TOKENS] = BudgetStatus(
            dimension=BudgetDimension.TOKENS,
            used=self.tokens_used,
            limit=self.token_budget,
            percentage=token_pct,
            is_exceeded=self.tokens_used >= self.token_budget,
            is_critical=token_pct >= self.critical_threshold,
        )

        # Time budget
        time_budget_seconds = self.time_budget.total_seconds()
        time_pct = (
            time_elapsed.total_seconds() / time_budget_seconds
            if time_budget_seconds > 0
            else 0
        )
        statuses[BudgetDimension.TIME] = BudgetStatus(
            dimension=BudgetDimension.TIME,
            used=time_elapsed.total_seconds(),
            limit=time_budget_seconds,
            percentage=time_pct,
            is_exceeded=time_elapsed >= self.time_budget
            if time_budget_seconds > 0
            else False,
            is_critical=time_pct >= self.critical_threshold,
        )

        # Cost budget
        cost_pct = self.cost_incurred / self.cost_budget if self.cost_budget > 0 else 0
        statuses[BudgetDimension.COST] = BudgetStatus(
            dimension=BudgetDimension.COST,
            used=self.cost_incurred,
            limit=self.cost_budget,
            percentage=cost_pct,
            is_exceeded=self.cost_incurred >= self.cost_budget,
            is_critical=cost_pct >= self.critical_threshold,
        )

        # Iteration budget
        iter_pct = (
            self.iterations_done / self.iteration_budget
            if self.iteration_budget > 0
            else 0
        )
        statuses[BudgetDimension.ITERATIONS] = BudgetStatus(
            dimension=BudgetDimension.ITERATIONS,
            used=self.iterations_done,
            limit=self.iteration_budget,
            percentage=iter_pct,
            is_exceeded=self.iterations_done >= self.iteration_budget,
            is_critical=iter_pct >= self.critical_threshold,
        )

        return statuses

    async def should_continue(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if execution should continue.
        Returns (should_continue, reason_if_not).
        """
        async with self._lock:
            statuses = await self.check_budgets_locked()

            # Check hard limits
            for status in statuses.values():
                if status.is_exceeded:
                    return False, f"{status.dimension.value} budget exceeded"

            # Check failure limit
            if self.consecutive_failures >= self.max_consecutive_failures:
                return (
                    False,
                    f"Too many consecutive failures ({self.consecutive_failures})",
                )

        return True, None

    async def should_enter_beast_mode(self) -> bool:
        """Check if we should force completion (beast mode)"""
        async with self._lock:
            statuses = await self.check_budgets_locked()

            # Enter beast mode if any budget is exceeded
            exceeded_statuses = [
                status for status in statuses.values() if status.is_exceeded
            ]
            if exceeded_statuses:
                for status in exceeded_statuses:
                    logger.info(f"Exceeded budget: {status}")
                logger.info("Entering beast mode due to exceeded budget")
                return True

            # Enter beast mode if any budget is critical
            critical_statuses = [
                status for status in statuses.values() if status.is_critical
            ]
            if critical_statuses:
                for status in critical_statuses:
                    logger.info(f"Critical budget: {status}")
                logger.info("Entering beast mode due to critical budget status")
                return True

            # Or if we're about to hit failure limit
            if self.consecutive_failures >= self.max_consecutive_failures - 1:
                logger.info("Entering beast mode due to imminent failure limit")
                return True

        return False

    async def should_be_conservative(self) -> bool:
        """Check if we should be conservative with resources"""
        async with self._lock:
            statuses = await self.check_budgets_locked()

            # Be conservative if any budget is above warning threshold
            return any(
                status.percentage >= self.warning_threshold
                for status in statuses.values()
            )

    async def record_action_failure(self, action: ActionType, error: str) -> None:
        """Record a failed action and update constraints"""
        async with self._lock:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.failure_by_action[action.value] = (
                self.failure_by_action.get(action.value, 0) + 1
            )

        logger.warning(f"Action {action.value} failed: {error}")
        logger.debug(f"Consecutive failures: {self.consecutive_failures}")

        # Disable the action temporarily
        self.disabled_actions.add(action)

        # Set cooldown based on failure count
        failure_count = self.failure_by_action[action.value]
        if failure_count >= self.failure_threshold_for_long_cooldown:
            # Long cooldown for repeated failures
            self.action_cooldowns[action] = datetime.now(timezone.utc) + timedelta(
                minutes=self.long_cooldown_minutes
            )
        else:
            # Short cooldown for occasional failures
            self.action_cooldowns[action] = datetime.now(timezone.utc) + timedelta(
                minutes=self.short_cooldown_minutes
            )

    async def record_action_success(self, action: ActionType) -> None:
        """Record successful action execution"""
        async with self._lock:
            self.consecutive_failures = 0

            # Re-enable action if it was disabled (unless too many total failures)
            if (
                action in self.disabled_actions
                and self.failure_by_action.get(action.value, 0)
                < self.max_failures_for_re_enable
            ):
                self.disabled_actions.remove(action)
                logger.debug(f"Re-enabled action: {action.value}")

    async def is_action_allowed(self, action: ActionType) -> Tuple[bool, Optional[str]]:
        """
        Check if an action is currently allowed.
        Returns (is_allowed, reason_if_not).
        """
        # Take a snapshot under lock to avoid race conditions
        async with self._lock:
            is_disabled = action in self.disabled_actions
            cooldown_time = self.action_cooldowns.get(action)
            active_subagents_count = self.active_subagents

        # Check if explicitly disabled
        if is_disabled:
            return False, "Action temporarily disabled due to failures"

        # Check cooldown
        if cooldown_time:
            if datetime.now(timezone.utc) < cooldown_time:
                remaining = (cooldown_time - datetime.now(timezone.utc)).total_seconds()
                return False, f"Action on cooldown for {remaining:.0f} more seconds"

        # Check resource constraints
        if await self.should_be_conservative():
            # Limit expensive actions when resources are low
            if action in self.conservative_restricted_actions:
                return False, "Conserving resources - budget running low"

        # Check specific action constraints
        if action == ActionType.CREATE_SUBAGENT:
            if active_subagents_count >= self.max_concurrent_subagents:
                return (
                    False,
                    f"Maximum concurrent subagents ({self.max_concurrent_subagents}) reached",
                )

        return True, None

    async def get_budget_summary(self) -> str:
        """Get a human-readable budget summary"""
        statuses = await self.check_budgets()
        lines = ["Budget Status:"]

        for status in statuses.values():
            emoji = "🔴" if status.is_exceeded else "🟡" if status.is_critical else "🟢"
            lines.append(f"  {emoji} {status}")

        if self.consecutive_failures > 0:
            lines.append(
                f"  ⚠️  Consecutive failures: {self.consecutive_failures}/{self.max_consecutive_failures}"
            )

        if self.disabled_actions:
            lines.append(
                f"  🚫 Disabled actions: {', '.join(a.value for a in self.disabled_actions)}"
            )

        return "\n".join(lines)

    async def estimate_remaining_capacity_locked(self) -> Dict[str, int]:
        """Internal version that assumes lock is held"""
        # Calculate remaining capacity for each dimension
        remaining = {}

        # Iterations are straightforward
        remaining["iterations"] = max(0, self.iteration_budget - self.iterations_done)

        # Estimate operations based on average usage
        if self.iterations_done > 0:
            avg_tokens_per_iter = self.tokens_used / self.iterations_done
            remaining["iterations_by_tokens"] = (
                int((self.token_budget - self.tokens_used) / avg_tokens_per_iter)
                if avg_tokens_per_iter > 0
                else 0
            )

            avg_cost_per_iter = self.cost_incurred / self.iterations_done
            remaining["iterations_by_cost"] = (
                int((self.cost_budget - self.cost_incurred) / avg_cost_per_iter)
                if avg_cost_per_iter > 0
                else 0
            )

            time_elapsed = self.get_time_elapsed()
            avg_time_per_iter = time_elapsed.total_seconds() / self.iterations_done
            time_remaining = (
                self.time_budget.total_seconds() - time_elapsed.total_seconds()
            )
            remaining["iterations_by_time"] = (
                int(time_remaining / avg_time_per_iter) if avg_time_per_iter > 0 else 0
            )
        else:
            remaining["iterations_by_tokens"] = self.iteration_budget
            remaining["iterations_by_cost"] = self.iteration_budget
            remaining["iterations_by_time"] = self.iteration_budget

        # The actual remaining is the minimum across all dimensions
        remaining["estimated_total"] = min(
            remaining["iterations"],
            remaining["iterations_by_tokens"],
            remaining["iterations_by_cost"],
            remaining["iterations_by_time"],
        )

        return remaining

    async def estimate_remaining_capacity(self) -> Dict[str, int]:
        """Estimate how many more operations we can do"""
        async with self._lock:
            return await self.estimate_remaining_capacity_locked()
