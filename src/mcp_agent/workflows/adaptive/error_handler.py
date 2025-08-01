"""
Enhanced Error Handling for AdaptiveWorkflow
Provides comprehensive error tracking, recovery suggestions, and debugging support
"""

import asyncio
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels"""

    LOW = "low"  # Can continue with warnings
    MEDIUM = "medium"  # May affect quality but can continue
    HIGH = "high"  # Should attempt recovery
    CRITICAL = "critical"  # Must stop or use emergency fallback


class ErrorCategory(str, Enum):
    """Categories of errors for better handling"""

    LLM_ERROR = "llm_error"  # LLM API errors
    VALIDATION_ERROR = "validation_error"  # Result validation failures
    RESOURCE_ERROR = "resource_error"  # Budget/resource exhaustion
    NETWORK_ERROR = "network_error"  # Network/connectivity issues
    LOGIC_ERROR = "logic_error"  # Workflow logic errors
    UNKNOWN_ERROR = "unknown_error"  # Unclassified errors


@dataclass
class ErrorContext:
    """Comprehensive error context for debugging"""

    error_type: type
    error_message: str
    traceback_str: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR

    # Context information
    workflow_stage: Optional[str] = None
    iteration: Optional[int] = None
    subtask_name: Optional[str] = None
    agent_name: Optional[str] = None

    # Additional debugging info
    context_data: Dict[str, Any] = field(default_factory=dict)
    recovery_attempted: bool = False
    recovery_strategy: Optional[str] = None


class WorkflowErrorHandler:
    """Enhanced error handler for AdaptiveWorkflow"""

    def __init__(self):
        self.error_history: List[ErrorContext] = []
        self.error_counts: Dict[ErrorCategory, int] = {}
        self._lock = asyncio.Lock()

        self.recovery_strategies: Dict[ErrorCategory, List[str]] = {
            ErrorCategory.LLM_ERROR: [
                "Retry with exponential backoff",
                "Switch to a different model",
                "Simplify the prompt",
                "Break down into smaller tasks",
            ],
            ErrorCategory.VALIDATION_ERROR: [
                "Re-run with different parameters",
                "Use a more conservative approach",
                "Add additional validation constraints",
                "Manually review results",
            ],
            ErrorCategory.RESOURCE_ERROR: [
                "Enter beast mode for quick completion",
                "Prune less important tasks",
                "Increase resource limits",
                "Save checkpoint and resume later",
            ],
            ErrorCategory.NETWORK_ERROR: [
                "Retry after delay",
                "Use cached results if available",
                "Switch to offline mode",
                "Check connectivity",
            ],
            ErrorCategory.LOGIC_ERROR: [
                "Review workflow configuration",
                "Check task dependencies",
                "Validate input parameters",
                "Enable debug logging",
            ],
        }

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type and message"""
        error_str = str(error).lower()

        # LLM/API errors
        if any(
            keyword in error_str
            for keyword in ["api", "rate limit", "timeout", "model"]
        ):
            return ErrorCategory.LLM_ERROR

        # Validation errors
        if any(
            keyword in error_str for keyword in ["validation", "invalid", "confidence"]
        ):
            return ErrorCategory.VALIDATION_ERROR

        # Resource errors
        if any(
            keyword in error_str
            for keyword in ["budget", "exceeded", "limit", "resource"]
        ):
            return ErrorCategory.RESOURCE_ERROR

        # Network errors
        if any(
            keyword in error_str
            for keyword in ["network", "connection", "http", "socket"]
        ):
            return ErrorCategory.NETWORK_ERROR

        # Logic errors
        if any(
            keyword in error_str
            for keyword in ["assertion", "attribute", "key", "index"]
        ):
            return ErrorCategory.LOGIC_ERROR

        return ErrorCategory.UNKNOWN_ERROR

    def determine_severity(
        self, error: Exception, context: Dict[str, Any]
    ) -> ErrorSeverity:
        """Determine error severity based on error and context"""
        # Critical errors that should stop execution
        if isinstance(error, (SystemExit, KeyboardInterrupt)):
            return ErrorSeverity.CRITICAL

        # Resource exhaustion is critical
        if "budget exceeded" in str(error).lower():
            return ErrorSeverity.CRITICAL

        # Validation failures are medium severity
        if "validation" in str(error).lower():
            return ErrorSeverity.MEDIUM

        # Network errors might be recoverable
        if "connection" in str(error).lower():
            return ErrorSeverity.HIGH

        # Default based on iteration count
        iteration = context.get("iteration", 0)
        if iteration > 5:  # Late in the process
            return ErrorSeverity.HIGH

        return ErrorSeverity.MEDIUM

    async def handle_error(
        self, error: Exception, workflow_stage: str, context: Dict[str, Any]
    ) -> ErrorContext:
        """
        Handle an error with full context capture

        Args:
            error: The exception that occurred
            workflow_stage: Current stage of workflow (e.g., "planning", "execution")
            context: Additional context data

        Returns:
            ErrorContext with all error information
        """
        # Capture full traceback
        tb_str = traceback.format_exc()

        # Categorize and determine severity
        category = self.categorize_error(error)
        severity = self.determine_severity(error, context)

        # Create error context
        error_context = ErrorContext(
            error_type=type(error),
            error_message=str(error),
            traceback_str=tb_str,
            severity=severity,
            category=category,
            workflow_stage=workflow_stage,
            iteration=context.get("iteration"),
            subtask_name=context.get("subtask_name"),
            agent_name=context.get("agent_name"),
            context_data=context,
        )

        # Track error
        async with self._lock:
            self.error_history.append(error_context)
            self.error_counts[category] = self.error_counts.get(category, 0) + 1

        # Log with appropriate level
        log_message = self._format_error_log(error_context)
        if severity == ErrorSeverity.CRITICAL:
            logger.error(log_message, exc_info=True)
        elif severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        else:
            logger.warning(log_message)

        # Log recovery suggestions
        if recovery_strategies := self.get_recovery_suggestions(error_context):
            logger.info(f"Suggested recovery strategies: {recovery_strategies}")

        return error_context

    def _format_error_log(self, error_context: ErrorContext) -> str:
        """Format error for logging with context"""
        parts = [
            f"[{error_context.severity.value.upper()}]",
            f"{error_context.category.value}:",
            error_context.error_message,
            f"at {error_context.workflow_stage}",
        ]

        if error_context.iteration is not None:
            parts.append(f"(iteration {error_context.iteration})")

        if error_context.subtask_name:
            parts.append(f"in subtask '{error_context.subtask_name}'")

        return " ".join(parts)

    def get_recovery_suggestions(self, error_context: ErrorContext) -> List[str]:
        """Get recovery suggestions based on error category"""
        base_suggestions = self.recovery_strategies.get(
            error_context.category, ["Check logs for details", "Retry operation"]
        )

        # Add specific suggestions based on context
        suggestions = base_suggestions.copy()

        # If we've seen this error multiple times, suggest more drastic measures
        error_count = self.error_counts.get(error_context.category, 0)
        if error_count > 3:
            suggestions.append("Consider restarting with different configuration")

        # Specific suggestions based on workflow stage
        if error_context.workflow_stage == "planning":
            suggestions.append("Simplify the objective or break it into phases")
        elif error_context.workflow_stage == "execution":
            suggestions.append("Skip this subtask and continue with others")

        return suggestions

    def should_retry(self, error_context: ErrorContext) -> bool:
        """Determine if the operation should be retried"""
        # Don't retry critical errors
        if error_context.severity == ErrorSeverity.CRITICAL:
            return False

        # Network and LLM errors are often transient
        if error_context.category in [
            ErrorCategory.NETWORK_ERROR,
            ErrorCategory.LLM_ERROR,
        ]:
            error_count = self.error_counts.get(error_context.category, 0)
            return error_count < 3  # Retry up to 3 times

        # Don't retry logic errors
        if error_context.category == ErrorCategory.LOGIC_ERROR:
            return False

        return True

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of all errors encountered"""
        return {
            "total_errors": len(self.error_history),
            "by_category": dict(self.error_counts),
            "by_severity": {
                severity.value: sum(
                    1 for e in self.error_history if e.severity == severity
                )
                for severity in ErrorSeverity
            },
            "recent_errors": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "category": e.category.value,
                    "severity": e.severity.value,
                    "message": e.error_message,
                    "stage": e.workflow_stage,
                }
                for e in self.error_history[-5:]  # Last 5 errors
            ],
        }

    def create_debug_report(self) -> str:
        """Create a detailed debug report for troubleshooting"""
        report_lines = [
            "=== AdaptiveWorkflow Error Report ===",
            f"Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"Total errors: {len(self.error_history)}",
            "",
            "Error Summary by Category:",
        ]

        for category, count in self.error_counts.items():
            report_lines.append(f"  {category.value}: {count}")

        report_lines.extend(["", "Recent Errors (last 5):", "-" * 50])

        for error in self.error_history[-5:]:
            report_lines.extend(
                [
                    f"\nError at {error.timestamp.isoformat()}:",
                    f"  Category: {error.category.value}",
                    f"  Severity: {error.severity.value}",
                    f"  Stage: {error.workflow_stage}",
                    f"  Message: {error.error_message}",
                    f"  Subtask: {error.subtask_name or 'N/A'}",
                    "",
                ]
            )

            if error.recovery_attempted:
                report_lines.append(f"  Recovery attempted: {error.recovery_strategy}")

        report_lines.extend(
            ["", "For full stack traces, check the log files.", "=== End of Report ==="]
        )

        return "\n".join(report_lines)
