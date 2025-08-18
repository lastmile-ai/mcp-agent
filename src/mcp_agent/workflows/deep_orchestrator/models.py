"""
Data models for the Deep Orchestrator workflow.

This module contains all the Pydantic models and dataclasses used by the
Deep Orchestrator for task planning, execution, and result tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # For dependency failures


class PolicyAction(str, Enum):
    """Actions the policy engine can recommend."""

    CONTINUE = "continue"
    REPLAN = "replan"
    FORCE_COMPLETE = "force_complete"
    EMERGENCY_STOP = "emergency_stop"


# ============================================================================
# Knowledge and Memory Models
# ============================================================================


@dataclass
class KnowledgeItem:
    """A piece of extracted knowledge from task execution."""

    key: str
    value: Any
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0
    category: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "category": self.category,
        }


@dataclass
class TaskResult:
    """Result from executing a task."""

    task_name: str  # Primary identifier for the task
    status: TaskStatus
    output: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    knowledge_extracted: List[KnowledgeItem] = field(default_factory=list)
    duration_seconds: float = 0.0
    retry_count: int = 0

    @property
    def success(self) -> bool:
        """Check if the task was successful."""
        return self.status == TaskStatus.COMPLETED


# ============================================================================
# Planning Models
# ============================================================================


class Task(BaseModel):
    """Individual task which can be accomplished by a single subagent."""

    description: str = Field(
        description="Clear, specific description of what needs to be done"
    )

    name: str = Field(
        description="Unique name for this task that can be referenced by other tasks"
    )

    agent: Optional[str] = Field(
        default=None,
        description="Agent name for this task, leave unset for dynamic creation",
    )
    servers: List[str] = Field(default_factory=list, description="Required MCP servers")

    # Context requirements
    requires_context_from: List[str] = Field(
        default_factory=list,
        description="List of previous task names whose outputs should be included in context",
    )
    context_window_budget: int = Field(
        default=10000, description="Maximum tokens of context this task needs"
    )

    # Runtime fields
    status: TaskStatus = Field(default=TaskStatus.PENDING)

    def get_hash_key(self) -> Tuple[str, ...]:
        """Get a hash key for deduplication."""
        return (self.description.strip().lower(), tuple(sorted(self.servers)))  # pylint: disable=E1101


class Step(BaseModel):
    """A step containing tasks that can run in parallel."""

    description: str = Field(description="What this step accomplishes")
    tasks: List[Task] = Field(description="Tasks that can run in parallel")

    # Runtime fields
    completed: bool = Field(default=False)


class Plan(BaseModel):
    """A complete execution plan."""

    steps: List[Step] = Field(description="Sequential steps to execute")
    is_complete: bool = Field(
        default=False, description="Whether objective is already satisfied"
    )
    reasoning: str = Field(default="", description="Explanation of the plan")


# ============================================================================
# Knowledge Extraction Models
# ============================================================================


class ExtractedKnowledge(BaseModel):
    """Model for knowledge extraction results."""

    items: List[Dict[str, Any]] = Field(
        description="Knowledge items with key, value, category, and confidence"
    )


# ============================================================================
# Agent Design Models
# ============================================================================


class AgentDesign(BaseModel):
    """Model for dynamically designed agents."""

    name: str = Field(
        description="Short, descriptive name (e.g., 'DataAnalyzer', 'ReportWriter')"
    )
    role: str = Field(description="The agent's specialty and expertise")
    instruction: str = Field(
        description="Detailed instruction for optimal task completion"
    )
    key_behaviors: List[str] = Field(
        description="Important behaviors the agent should exhibit"
    )
    tool_usage_tips: List[str] = Field(
        description="Specific tips for using the required tools"
    )


# ============================================================================
# Plan Verification Models
# ============================================================================


class PlanVerificationError(BaseModel):
    """Individual error found during plan verification."""

    category: str = Field(
        description="Error category (e.g., 'invalid_server', 'duplicate_name')"
    )
    message: str = Field(description="Human-readable error message")
    step_index: Optional[int] = Field(
        default=None, description="Step index where error occurred (0-based)"
    )
    task_name: Optional[str] = Field(
        default=None, description="Task name where error occurred"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional error details"
    )


class PlanVerificationResult(BaseModel):
    """Result of plan verification with all collected errors."""

    is_valid: bool = Field(description="Whether the plan is valid")
    errors: List[PlanVerificationError] = []
    warnings: List[str] = []

    def add_error(self, category: str, message: str, **kwargs) -> None:
        """Add an error to the verification result."""
        self.errors.append(
            PlanVerificationError(category=category, message=message, **kwargs)
        )
        self.is_valid = False

    def get_error_summary(self) -> str:
        """Get a formatted summary of all errors."""
        if self.is_valid:
            return "Plan is valid"

        lines = ["Plan verification failed with the following errors:"]

        # Group errors by category
        errors_by_category = {}
        for error in self.errors:
            if error.category not in errors_by_category:
                errors_by_category[error.category] = []
            errors_by_category[error.category].append(error)

        # Format each category
        for category, errors in errors_by_category.items():
            lines.append(f"\n{category.replace('_', ' ').title()}:")
            for error in errors:
                lines.append(f"  - {error.message}")
                if error.step_index is not None:
                    lines.append(f"    (Step {error.step_index + 1})")
                if error.task_name:
                    lines.append(f"    (Task: {error.task_name})")

        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)


# ============================================================================
# Verification Models
# ============================================================================


class VerificationResult(BaseModel):
    """Result of objective verification."""

    is_complete: bool = Field(description="Whether objective is satisfied")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level (0-1)")
    reasoning: str = Field(description="Detailed explanation of the assessment")
    missing_elements: List[str] = Field(
        default_factory=list, description="Critical missing elements"
    )
    achievements: List[str] = Field(
        default_factory=list, description="What was successfully completed"
    )
