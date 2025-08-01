"""
Data models for Adaptive Workflow V2 - Simplified Deep Research Architecture
"""

from enum import Enum
from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from typing_extensions import Annotated


class TaskType(str, Enum):
    """Types of tasks the workflow can handle"""

    RESEARCH = "research"  # Information gathering
    ACTION = "action"  # Making changes/executing operations
    HYBRID = "hybrid"  # Research followed by action


class ResearchAspect(BaseModel):
    """A specific aspect to research"""

    name: str = Field(description="Name of the aspect to research")
    objective: str = Field(description="What to find out about this aspect")
    required_servers: List[str] = Field(
        default_factory=list, description="MCP servers needed for this research"
    )
    use_predefined_agent: Optional[str] = Field(
        default=None,
        description="Name of predefined agent to use instead of creating new one",
    )


class SubagentResult(BaseModel):
    """Result from a subagent's research"""

    aspect_name: str
    findings: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None

    # Token tracking - populated from TokenCounter
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # Cost tracking - calculated from token usage
    cost: float = 0.0

    # Model info for cost calculation
    model_name: Optional[str] = None
    provider: Optional[str] = None

    # Validation results
    confidence: float = 0.7  # Default medium confidence
    validation_notes: Optional[str] = None


class SynthesisDecision(BaseModel):
    """Decision after synthesizing research results"""

    is_complete: bool = Field(
        description="Whether the research objective has been achieved"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence that the objective is complete"
    )
    reasoning: str = Field(description="Explanation of the decision")
    new_aspects: Optional[List[ResearchAspect]] = Field(
        default=None, description="New aspects to research if not complete"
    )


class ExecutionMemory(BaseModel):
    """Memory for adaptive execution"""

    execution_id: str
    objective: str
    task_type: Optional[TaskType] = None

    # Execution tracking
    start_time: Annotated[datetime, Field(default_factory=datetime.now)]
    iterations: int = 0

    # Research history - store as Any to handle provider-specific message types
    research_history: Annotated[
        List[Any],
        Field(
            default_factory=list, description="Synthesis messages from each iteration"
        ),
    ]
    subagent_results: Annotated[
        List[SubagentResult],
        Field(default_factory=list, description="All subagent results"),
    ]

    # Resource tracking
    total_cost: float = 0.0


class ExecutionResult(BaseModel):
    """Final result of the adaptive execution"""

    execution_id: str
    objective: str
    task_type: TaskType

    # Results - store as Any to handle provider-specific message types
    result_messages: Any = Field(description="The final result as LLM messages")
    confidence: float = Field(ge=0.0, le=1.0)

    # Metrics
    iterations: int
    subagents_used: int
    total_time_seconds: float
    total_cost: float

    # Token usage metrics
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    # Status
    success: bool = True
    limitations: List[str] = Field(default_factory=list)
