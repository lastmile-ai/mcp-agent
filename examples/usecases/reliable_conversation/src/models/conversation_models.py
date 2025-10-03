"""
Conversation models for Reliable Conversation Manager.
Based on the research findings from "LLMs Get Lost in Multi-Turn Conversation".
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any


@dataclass
class ConversationMessage:
    """Single message in conversation - matches paper's Message model"""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    turn_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "turn_number": self.turn_number,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMessage":
        """Create from dictionary"""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            turn_number=data["turn_number"],
        )


@dataclass
class Requirement:
    """Tracked requirement from paper Section 5.1"""

    id: str
    description: str
    source_turn: int
    status: Literal["pending", "addressed", "confirmed"] = "pending"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "description": self.description,
            "source_turn": self.source_turn,
            "status": self.status,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Requirement":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            description=data["description"],
            source_turn=data["source_turn"],
            status=data["status"],
            confidence=data["confidence"],
        )


@dataclass
class QualityMetrics:
    """From paper Table 1 - all metrics 0-1 scale"""

    clarity: float
    completeness: float
    assumptions: float  # Lower is better
    verbosity: float  # Lower is better
    premature_attempt: bool = False
    middle_turn_reference: float = 0.0
    requirement_tracking: float = 0.0

    @property
    def overall_score(self) -> float:
        """Paper's composite scoring formula"""
        base = (
            self.clarity
            + self.completeness
            + self.middle_turn_reference
            + self.requirement_tracking
            + (1 - self.assumptions)
            + (1 - self.verbosity)
        ) / 6
        if self.premature_attempt:
            base *= 0.5  # Heavy penalty from paper
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "clarity": self.clarity,
            "completeness": self.completeness,
            "assumptions": self.assumptions,
            "verbosity": self.verbosity,
            "premature_attempt": self.premature_attempt,
            "middle_turn_reference": self.middle_turn_reference,
            "requirement_tracking": self.requirement_tracking,
            "overall_score": self.overall_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityMetrics":
        """Create from dictionary"""
        return cls(
            clarity=data["clarity"],
            completeness=data["completeness"],
            assumptions=data["assumptions"],
            verbosity=data["verbosity"],
            premature_attempt=data["premature_attempt"],
            middle_turn_reference=data["middle_turn_reference"],
            requirement_tracking=data["requirement_tracking"],
        )


@dataclass
class ConversationState:
    """Complete conversation state - maintained in workflow"""

    conversation_id: str
    messages: List[ConversationMessage] = field(default_factory=list)
    requirements: List[Requirement] = field(default_factory=list)
    consolidated_context: str = ""
    quality_history: List[QualityMetrics] = field(default_factory=list)
    current_turn: int = 0

    # Paper metrics
    first_answer_attempt_turn: Optional[int] = None
    answer_lengths: List[int] = field(default_factory=list)
    consolidation_turns: List[int] = field(default_factory=list)

    # Execution state
    is_temporal_mode: bool = False
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "conversation_id": self.conversation_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "requirements": [req.to_dict() for req in self.requirements],
            "consolidated_context": self.consolidated_context,
            "quality_history": [qm.to_dict() for qm in self.quality_history],
            "current_turn": self.current_turn,
            "first_answer_attempt_turn": self.first_answer_attempt_turn,
            "answer_lengths": self.answer_lengths,
            "consolidation_turns": self.consolidation_turns,
            "is_temporal_mode": self.is_temporal_mode,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        """Create from dictionary"""
        return cls(
            conversation_id=data["conversation_id"],
            messages=[ConversationMessage.from_dict(msg) for msg in data["messages"]],
            requirements=[Requirement.from_dict(req) for req in data["requirements"]],
            consolidated_context=data["consolidated_context"],
            quality_history=[
                QualityMetrics.from_dict(qm) for qm in data["quality_history"]
            ],
            current_turn=data["current_turn"],
            first_answer_attempt_turn=data.get("first_answer_attempt_turn"),
            answer_lengths=data["answer_lengths"],
            consolidation_turns=data["consolidation_turns"],
            is_temporal_mode=data["is_temporal_mode"],
            is_active=data["is_active"],
        )


@dataclass
class ConversationConfig:
    """Configuration for RCM operations"""

    quality_threshold: float = 0.8
    max_refinement_attempts: int = 3
    consolidation_interval: int = 3
    use_claude_code: bool = False
    evaluator_model_provider: str = "openai"
    verbose_metrics: bool = False
    max_turns: int = 50
    max_context_tokens: int = 8000
    mcp_servers: List[str] = field(default_factory=lambda: ["fetch", "filesystem"])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "quality_threshold": self.quality_threshold,
            "max_refinement_attempts": self.max_refinement_attempts,
            "consolidation_interval": self.consolidation_interval,
            "use_claude_code": self.use_claude_code,
            "evaluator_model_provider": self.evaluator_model_provider,
            "verbose_metrics": self.verbose_metrics,
            "max_turns": self.max_turns,
            "max_context_tokens": self.max_context_tokens,
            "mcp_servers": self.mcp_servers,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationConfig":
        """Create from dictionary"""
        return cls(
            quality_threshold=data.get("quality_threshold", 0.8),
            max_refinement_attempts=data.get("max_refinement_attempts", 3),
            consolidation_interval=data.get("consolidation_interval", 3),
            use_claude_code=data.get("use_claude_code", False),
            evaluator_model_provider=data.get("evaluator_model_provider", "openai"),
            verbose_metrics=data.get("verbose_metrics", False),
            max_turns=data.get("max_turns", 50),
            max_context_tokens=data.get("max_context_tokens", 8000),
            mcp_servers=data.get("mcp_servers", ["fetch", "filesystem"]),
        )
