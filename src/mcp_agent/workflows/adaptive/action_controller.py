"""
Action Control System for AdaptiveWorkflow
Manages action availability based on system state and history
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Set, List, Optional, Any, Tuple
from enum import Enum

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class WorkflowAction(str, Enum):
    """All possible workflow actions"""

    ANALYZE = "analyze"
    PLAN = "plan"
    EXECUTE_SUBTASK = "execute_subtask"
    SYNTHESIZE = "synthesize"
    DECIDE = "decide"
    CONCLUDE = "conclude"
    CREATE_SUBAGENT = "create_subagent"
    EXTRACT_KNOWLEDGE = "extract_knowledge"
    REFLECT = "reflect"
    DECOMPOSE = "decompose"


@dataclass
class ActionHistoryEntry:
    """Record of an action execution"""

    action: WorkflowAction
    success: bool
    timestamp: datetime
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionConstraints:
    """Constraints for a specific action"""

    min_knowledge_items: int = 0
    min_iterations: int = 0
    max_attempts_per_iteration: int = 3
    cooldown_minutes: int = 0
    requires_findings: bool = False
    requires_synthesis: bool = False
    max_concurrent: int = 1


class ActionController:
    """Controls which actions are available based on system state"""

    def __init__(
        self,
        constraints: Optional[Dict[WorkflowAction, ActionConstraints]] = None,
        max_consecutive_failures: int = 3,
        failure_cooldown_multiplier: float = 5.0,
        success_recovery_threshold: int = 2,
        min_confidence_for_conclusion: float = 0.7,
    ):
        self.action_history: List[ActionHistoryEntry] = []
        self.disabled_actions: Set[WorkflowAction] = set()
        self.action_cooldowns: Dict[WorkflowAction, datetime] = {}
        self.current_iteration: int = 0

        # Configurable parameters
        self.max_consecutive_failures = max_consecutive_failures
        self.failure_cooldown_multiplier = failure_cooldown_multiplier
        self.success_recovery_threshold = success_recovery_threshold
        self.min_confidence_for_conclusion = min_confidence_for_conclusion

        # Create lock immediately - safe to create outside async context
        self._lock = asyncio.Lock()

        # Define action constraints (use provided or defaults)
        self.constraints: Dict[WorkflowAction, ActionConstraints] = constraints or {
            WorkflowAction.ANALYZE: ActionConstraints(
                max_attempts_per_iteration=1  # Only analyze once per workflow
            ),
            WorkflowAction.PLAN: ActionConstraints(
                max_attempts_per_iteration=2, cooldown_minutes=1
            ),
            WorkflowAction.EXECUTE_SUBTASK: ActionConstraints(
                max_concurrent=5  # Limit concurrent subtasks
            ),
            WorkflowAction.SYNTHESIZE: ActionConstraints(
                min_knowledge_items=2, requires_findings=True, cooldown_minutes=2
            ),
            WorkflowAction.DECIDE: ActionConstraints(
                requires_synthesis=True, max_attempts_per_iteration=1
            ),
            WorkflowAction.CONCLUDE: ActionConstraints(
                min_knowledge_items=3, min_iterations=1, requires_synthesis=True
            ),
            WorkflowAction.CREATE_SUBAGENT: ActionConstraints(
                max_concurrent=5, cooldown_minutes=1
            ),
            WorkflowAction.EXTRACT_KNOWLEDGE: ActionConstraints(requires_findings=True),
            WorkflowAction.REFLECT: ActionConstraints(
                min_iterations=1, cooldown_minutes=3
            ),
            WorkflowAction.DECOMPOSE: ActionConstraints(max_attempts_per_iteration=2),
        }

    async def update_iteration(self, iteration: int) -> None:
        """Update current iteration number"""
        async with self._lock:
            self.current_iteration = iteration

    async def is_action_available(
        self, action: WorkflowAction, context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if an action can be performed.
        Returns (is_available, reason_if_not).
        """
        async with self._lock:
            # Check if explicitly disabled
            if action in self.disabled_actions:
                return False, "Action is currently disabled"

            # Check cooldown
            if action in self.action_cooldowns:
                if datetime.now(timezone.utc) < self.action_cooldowns[action]:
                    remaining = (
                        self.action_cooldowns[action] - datetime.now(timezone.utc)
                    ).total_seconds()
                    return False, f"Action on cooldown for {remaining:.0f} more seconds"

            # Get constraints for this action
            constraints = self.constraints.get(action, ActionConstraints())

            # Check iteration-based constraints
            if self.current_iteration < constraints.min_iterations:
                return (
                    False,
                    f"Requires at least {constraints.min_iterations} iterations",
                )

            # Check attempts in current iteration
            recent_attempts = self._get_recent_attempts(action, self.current_iteration)
            if len(recent_attempts) >= constraints.max_attempts_per_iteration:
                return (
                    False,
                    f"Maximum attempts ({constraints.max_attempts_per_iteration}) reached for this iteration",
                )

            # Check knowledge requirements
            knowledge_count = len(context.get("knowledge_items", []))
            if knowledge_count < constraints.min_knowledge_items:
                return (
                    False,
                    f"Requires at least {constraints.min_knowledge_items} knowledge items (have {knowledge_count})",
                )

            # Check specific requirements
            if constraints.requires_findings and not context.get("has_findings", False):
                return False, "Requires research findings"

            if constraints.requires_synthesis and not context.get(
                "has_synthesis", False
            ):
                return False, "Requires synthesis to be completed"

            # Check concurrent execution limits
            if constraints.max_concurrent > 1:
                active_count = context.get(f"active_{action.value}_count", 0)
                if active_count >= constraints.max_concurrent:
                    return (
                        False,
                        f"Maximum concurrent {action.value} ({constraints.max_concurrent}) reached",
                    )

            # Action-specific checks
            return self._check_action_specific_constraints(action, context)

    def _check_action_specific_constraints(
        self, action: WorkflowAction, context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Check constraints specific to each action"""
        if action == WorkflowAction.ANALYZE:
            # Only analyze once at the beginning
            if any(
                h.action == WorkflowAction.ANALYZE and h.success
                for h in self.action_history
            ):
                return False, "Analysis already completed"

        elif action == WorkflowAction.CONCLUDE:
            # Check if we have enough confidence to conclude
            confidence = context.get("confidence", 0.0)
            if confidence < self.min_confidence_for_conclusion:
                return (
                    False,
                    f"Confidence too low to conclude ({confidence:.2f} < {self.min_confidence_for_conclusion})",
                )

        elif action == WorkflowAction.DECOMPOSE:
            # Only decompose complex subtasks
            subtask_complexity = context.get("subtask_complexity", 0)
            if subtask_complexity < 2:
                return False, "Subtask not complex enough to decompose"

        return True, None

    async def record_action(
        self,
        action: WorkflowAction,
        success: bool,
        duration: Optional[float] = None,
        error: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record action execution and update constraints"""
        async with self._lock:
            entry = ActionHistoryEntry(
                action=action,
                success=success,
                timestamp=datetime.now(timezone.utc),
                duration_seconds=duration,
                error=error,
                context=context or {},
            )
            self.action_history.append(entry)

            if not success:
                await self._handle_failure_locked(action, error)
            else:
                await self._handle_success_locked(action)

        logger.debug(
            f"Recorded action {action.value}: {'success' if success else 'failure'}"
        )

    async def _handle_failure_locked(
        self, action: WorkflowAction, error: Optional[str]
    ) -> None:
        """Handle action failure - assumes lock is held"""
        # Count recent failures (including the one just recorded)
        recent_failures = [
            h for h in self.action_history[-10:] if h.action == action and not h.success
        ]

        constraints = self.constraints.get(action, ActionConstraints())

        # Apply cooldown
        if constraints.cooldown_minutes > 0:
            self.action_cooldowns[action] = datetime.now(timezone.utc) + timedelta(
                minutes=constraints.cooldown_minutes
            )

        # Disable action if too many failures (check after recording this failure)
        if len(recent_failures) >= self.max_consecutive_failures:
            self.disabled_actions.add(action)
            logger.warning(
                f"Disabled action {action.value} due to {len(recent_failures)} repeated failures"
            )

    async def _handle_success_locked(self, action: WorkflowAction) -> None:
        """Handle action success - assumes lock is held"""
        # Remove from disabled if it was there
        if action in self.disabled_actions:
            # Check if we should re-enable
            recent_successes = [
                h for h in self.action_history[-5:] if h.action == action and h.success
            ]
            if len(recent_successes) >= self.success_recovery_threshold:
                self.disabled_actions.remove(action)
                logger.info(
                    f"Re-enabled action {action.value} after {len(recent_successes)} successful executions"
                )

    def _get_recent_attempts(
        self, action: WorkflowAction, iteration: int
    ) -> List[ActionHistoryEntry]:
        """Get attempts for an action in the current iteration

        NOTE: This method assumes the caller holds self._lock
        """
        return [
            h
            for h in self.action_history
            if h.action == action and h.context.get("iteration", 0) == iteration
        ]

    async def get_available_actions(
        self, context: Dict[str, Any]
    ) -> List[WorkflowAction]:
        """Get list of currently available actions"""
        available = []
        for action in WorkflowAction:
            is_available, _ = await self.is_action_available(action, context)
            if is_available:
                available.append(action)
        return available

    async def get_recommended_action(
        self, context: Dict[str, Any]
    ) -> Optional[WorkflowAction]:
        """Get recommended next action based on state"""
        available = await self.get_available_actions(context)
        if not available:
            return None

        # Priority order based on workflow state
        priority_order = [
            WorkflowAction.ANALYZE,  # First priority if not done
            WorkflowAction.PLAN,  # Plan next steps
            WorkflowAction.EXECUTE_SUBTASK,  # Execute planned work
            WorkflowAction.EXTRACT_KNOWLEDGE,  # Extract from findings
            WorkflowAction.SYNTHESIZE,  # Synthesize when enough knowledge
            WorkflowAction.DECIDE,  # Decide next steps
            WorkflowAction.CONCLUDE,  # Conclude if confident
            WorkflowAction.REFLECT,  # Reflect if stuck
            WorkflowAction.DECOMPOSE,  # Decompose complex tasks
        ]

        # Return first available action in priority order
        for action in priority_order:
            if action in available:
                return action

        # Fallback to first available
        return available[0] if available else None

    async def get_action_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics about action usage"""
        async with self._lock:
            # Create a copy of the data while holding lock
            stats = {}
            for action in WorkflowAction:
                action_entries = [h for h in self.action_history if h.action == action]
                successful = [h for h in action_entries if h.success]
                failed = [h for h in action_entries if not h.success]

                avg_duration = None
                if successful:
                    durations = [
                        h.duration_seconds for h in successful if h.duration_seconds
                    ]
                    if durations:
                        avg_duration = sum(durations) / len(durations)

                stats[action.value] = {
                    "total_attempts": len(action_entries),
                    "successful": len(successful),
                    "failed": len(failed),
                    "success_rate": len(successful) / len(action_entries)
                    if action_entries
                    else 0,
                    "average_duration": avg_duration,
                    "is_disabled": action in self.disabled_actions,
                    "on_cooldown": action in self.action_cooldowns,
                }
            return stats

    async def suggest_recovery_action(
        self, failed_action: WorkflowAction, error: str, context: Dict[str, Any]
    ) -> Optional[WorkflowAction]:
        """Suggest a recovery action after failure"""
        # Map failures to recovery actions
        recovery_map = {
            WorkflowAction.EXECUTE_SUBTASK: WorkflowAction.DECOMPOSE,  # Break down if execution fails
            WorkflowAction.SYNTHESIZE: WorkflowAction.EXECUTE_SUBTASK,  # Get more data
            WorkflowAction.CONCLUDE: WorkflowAction.REFLECT,  # Reflect if can't conclude
            WorkflowAction.PLAN: WorkflowAction.REFLECT,  # Reflect if planning fails
        }

        recovery_action = recovery_map.get(failed_action)
        if recovery_action:
            is_available, _ = await self.is_action_available(recovery_action, context)
            if is_available:
                return recovery_action

        # Default to reflection if available
        is_available, _ = await self.is_action_available(
            WorkflowAction.REFLECT, context
        )
        if is_available:
            return WorkflowAction.REFLECT

        return None
