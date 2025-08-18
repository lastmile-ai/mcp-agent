"""
Budget management for the Deep Orchestrator workflow.

This module handles token, cost, and time budget tracking to prevent
runaway execution and provide resource monitoring.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SimpleBudget:
    """Lightweight budget tracker for resource management."""

    # Budget limits
    max_tokens: int = 100000
    max_cost: float = 10.0
    max_time_minutes: int = 30

    # Current usage
    tokens_used: int = 0
    cost_incurred: float = 0.0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Cost configuration
    cost_per_1k_tokens: float = 0.001

    def update_tokens(self, tokens: int) -> None:
        """
        Update token usage and cost.

        Args:
            tokens: Number of tokens to add to usage
        """
        self.tokens_used += tokens
        self.cost_incurred += (tokens / 1000) * self.cost_per_1k_tokens

        # logger.debug(
        #     f"Budget updated: tokens={self.tokens_used}/{self.max_tokens}, "
        #     f"cost=${self.cost_incurred:.3f}/${self.max_cost}"
        # )

    def is_exceeded(self) -> Tuple[bool, Optional[str]]:
        """
        Check if any budget dimension is exceeded.

        Returns:
            Tuple of (is_exceeded, reason_message)
        """
        # Check token budget
        if self.tokens_used >= self.max_tokens:
            return True, f"Token budget exceeded: {self.tokens_used}/{self.max_tokens}"

        # Check cost budget
        if self.cost_incurred >= self.max_cost:
            return (
                True,
                f"Cost budget exceeded: ${self.cost_incurred:.2f}/${self.max_cost}",
            )

        # Check time budget
        elapsed = datetime.now(timezone.utc) - self.start_time
        elapsed_minutes = elapsed.total_seconds() / 60
        if elapsed_minutes > self.max_time_minutes:
            return (
                True,
                f"Time budget exceeded: {elapsed_minutes:.1f}/{self.max_time_minutes} minutes",
            )

        return False, None

    def get_usage_pct(self) -> Dict[str, float]:
        """
        Get usage percentages for each budget dimension.

        Returns:
            Dictionary with usage percentages for tokens, cost, and time
        """
        elapsed = datetime.now(timezone.utc) - self.start_time
        elapsed_minutes = elapsed.total_seconds() / 60

        return {
            "tokens": self.tokens_used / self.max_tokens if self.max_tokens > 0 else 0,
            "cost": self.cost_incurred / self.max_cost if self.max_cost > 0 else 0,
            "time": elapsed_minutes / self.max_time_minutes
            if self.max_time_minutes > 0
            else 0,
        }

    def get_remaining(self) -> Dict[str, float]:
        """
        Get remaining budget for each dimension.

        Returns:
            Dictionary with remaining budget amounts
        """
        elapsed = datetime.now(timezone.utc) - self.start_time
        elapsed_minutes = elapsed.total_seconds() / 60

        return {
            "tokens": max(0, self.max_tokens - self.tokens_used),
            "cost": max(0, self.max_cost - self.cost_incurred),
            "time_minutes": max(0, self.max_time_minutes - elapsed_minutes),
        }

    def is_critical(self, threshold: float = 0.9) -> bool:
        """
        Check if any budget dimension is approaching critical levels.

        Args:
            threshold: Percentage threshold for critical level (default 0.9 = 90%)

        Returns:
            True if any dimension exceeds the threshold
        """
        usage = self.get_usage_pct()
        return any(v >= threshold for v in usage.values())

    def get_status_summary(self) -> str:
        """
        Get a human-readable status summary.

        Returns:
            String summary of budget status
        """
        usage = self.get_usage_pct()
        elapsed = datetime.now(timezone.utc) - self.start_time
        elapsed_minutes = elapsed.total_seconds() / 60

        return (
            f"Budget Status: "
            f"Tokens {self.tokens_used}/{self.max_tokens} ({usage['tokens']:.1%}), "
            f"Cost ${self.cost_incurred:.2f}/${self.max_cost} ({usage['cost']:.1%}), "
            f"Time {elapsed_minutes:.1f}/{self.max_time_minutes}min ({usage['time']:.1%})"
        )

    def reset(self) -> None:
        """Reset the budget tracker to initial state."""
        self.tokens_used = 0
        self.cost_incurred = 0.0
        self.start_time = datetime.now(timezone.utc)
        logger.info("Budget tracker reset")
