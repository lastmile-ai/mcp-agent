"""
Policy engine for the Deep Orchestrator workflow.

This module provides centralized decision-making for workflow control,
including when to replan, stop, or continue execution.
"""

from typing import Optional, Tuple

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.budget import SimpleBudget
from mcp_agent.workflows.deep_orchestrator.models import PolicyAction

logger = get_logger(__name__)


class PolicyEngine:
    """
    Centralized decision making for workflow control.

    The policy engine determines what action to take based on current state,
    including budget usage, failures, and verification results.
    """

    def __init__(
        self,
        max_consecutive_failures: int = 3,
        min_verification_confidence: float = 0.8,
        replan_on_empty_queue: bool = True,
        budget_critical_threshold: float = 0.9,
    ):
        """
        Initialize the policy engine.

        Args:
            max_consecutive_failures: Maximum allowed consecutive task failures
            min_verification_confidence: Minimum confidence for objective completion
            replan_on_empty_queue: Whether to replan when queue is empty
            budget_critical_threshold: Budget usage threshold for critical state
        """
        self.max_consecutive_failures = max_consecutive_failures
        self.min_verification_confidence = min_verification_confidence
        self.replan_on_empty_queue = replan_on_empty_queue
        self.budget_critical_threshold = budget_critical_threshold

        # Tracking state
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_successes = 0

        logger.info(
            f"Initialized PolicyEngine (max_failures={max_consecutive_failures}, "
            f"min_confidence={min_verification_confidence})"
        )

    def decide_action(
        self,
        queue_empty: bool,
        verification_result: Optional[Tuple[bool, float]],
        budget: SimpleBudget,
        iteration: int,
        max_iterations: int,
    ) -> PolicyAction:
        """
        Decide what action to take based on current state.

        Args:
            queue_empty: Whether the task queue is empty
            verification_result: Optional (is_complete, confidence) tuple
            budget: Current budget tracker
            iteration: Current iteration number
            max_iterations: Maximum allowed iterations

        Returns:
            Recommended policy action
        """
        # Check critical conditions first
        exceeded, reason = budget.is_exceeded()
        if exceeded:
            logger.warning(f"Budget exceeded: {reason}")
            return PolicyAction.FORCE_COMPLETE

        # Check if approaching budget limits
        if budget.is_critical(self.budget_critical_threshold):
            usage = budget.get_usage_pct()
            logger.warning(f"Approaching budget limits: {usage}")
            return PolicyAction.FORCE_COMPLETE

        # Check iteration limit
        if iteration >= max_iterations:
            logger.warning(f"Max iterations reached: {iteration}/{max_iterations}")
            return PolicyAction.FORCE_COMPLETE

        # Check failure threshold
        if self.consecutive_failures >= self.max_consecutive_failures:
            logger.error(f"Too many consecutive failures: {self.consecutive_failures}")
            return PolicyAction.EMERGENCY_STOP

        # Check if we need to replan
        if queue_empty:
            # Check if objective is verified complete
            if verification_result:
                is_complete, confidence = verification_result
                if is_complete and confidence >= self.min_verification_confidence:
                    logger.info(
                        f"Objective verified complete with confidence {confidence:.2f}"
                    )
                    return PolicyAction.CONTINUE

            # Queue empty and objective not verified
            if self.replan_on_empty_queue:
                logger.info(
                    "Queue empty and objective not verified, recommending replan"
                )
                return PolicyAction.REPLAN

        # Default action is to continue
        return PolicyAction.CONTINUE

    def record_success(self) -> None:
        """Record successful task execution."""
        self.consecutive_failures = 0
        self.total_successes += 1
        logger.debug(f"Success recorded (total: {self.total_successes})")

    def record_failure(self) -> None:
        """Record failed task execution."""
        self.consecutive_failures += 1
        self.total_failures += 1
        logger.debug(
            f"Failure recorded (consecutive: {self.consecutive_failures}, "
            f"total: {self.total_failures})"
        )

    def get_failure_rate(self) -> float:
        """
        Get the overall failure rate.

        Returns:
            Failure rate as a percentage (0.0 to 1.0)
        """
        total = self.total_successes + self.total_failures
        if total == 0:
            return 0.0
        return self.total_failures / total

    def should_retry_task(self, retry_count: int, max_retries: int = 3) -> bool:
        """
        Determine if a task should be retried.

        Args:
            retry_count: Current retry count for the task
            max_retries: Maximum allowed retries

        Returns:
            True if task should be retried
        """
        # Don't retry if we've hit the max
        if retry_count >= max_retries:
            return False

        # Don't retry if we're in a failure spiral
        if self.consecutive_failures >= self.max_consecutive_failures:
            return False

        # Consider overall failure rate
        failure_rate = self.get_failure_rate()
        if failure_rate > 0.5 and retry_count > 1:
            # High failure rate, be more conservative with retries
            return False

        return True

    def get_status_summary(self) -> str:
        """
        Get a human-readable status summary.

        Returns:
            String summary of policy engine state
        """
        failure_rate = self.get_failure_rate()
        return (
            f"Policy Status: "
            f"Successes={self.total_successes}, "
            f"Failures={self.total_failures} ({failure_rate:.1%}), "
            f"Consecutive failures={self.consecutive_failures}/{self.max_consecutive_failures}"
        )

    def reset(self) -> None:
        """Reset the policy engine state."""
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_successes = 0
        logger.info("Policy engine reset")
