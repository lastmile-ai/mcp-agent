"""
Knowledge Management System for AdaptiveWorkflow
Extracts, stores, and retrieves structured knowledge from research
"""

import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import json
from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.adaptive.models import SubagentResult, ExecutionMemory
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class KnowledgeType(str, Enum):
    """Types of knowledge we can extract"""

    FACT = "fact"
    ANSWER = "answer"
    RESOURCE = "resource"
    LIMITATION = "limitation"
    STRATEGY = "strategy"
    DEFINITION = "definition"
    EXAMPLE = "example"
    COMPARISON = "comparison"


class KnowledgeItem(BaseModel):
    """Structured knowledge extracted from research"""

    question: str
    answer: str
    confidence: float
    knowledge_type: KnowledgeType
    sources: List[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    used_count: int = 0
    relevance_score: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "question": self.question,
            "answer": self.answer,
            "confidence": self.confidence,
            "knowledge_type": self.knowledge_type.value,
            "sources": self.sources,
            "extracted_at": self.extracted_at.isoformat(),
            "used_count": self.used_count,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
        }

    def increment_usage(self) -> None:
        """Track when this knowledge is used"""
        self.used_count += 1
        self.relevance_score = min(2.0, self.relevance_score * 1.1)  # Boost relevance


class ActionDiaryEntry(BaseModel):
    """Record of an action taken during research"""

    iteration: int
    action: str
    details: Dict[str, Any]
    success: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "iteration": self.iteration,
            "action": self.action,
            "details": self.details,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
        }


class EnhancedExecutionMemory(ExecutionMemory):
    """Extended memory with knowledge management"""

    # Knowledge base
    knowledge_items: List[KnowledgeItem] = Field(default_factory=list)

    # Action diary (what was done)
    action_diary: List[ActionDiaryEntry] = Field(default_factory=list)

    # Failed attempts for learning
    failed_attempts: List[Dict[str, Any]] = Field(default_factory=list)

    # Current context size estimate (for budget management)
    context_tokens: int = 0

    # Knowledge index for fast retrieval - not serialized
    _knowledge_index: Optional[Dict[str, List[int]]] = None

    # Lock for thread-safe access - not serialized
    _lock: Optional[asyncio.Lock] = None

    class Config:
        arbitrary_types_allowed = True
        exclude = {"_knowledge_index", "_lock"}

    def __init__(self, **data):
        super().__init__(**data)
        self._lock = asyncio.Lock()

    async def add_knowledge_items(self, items: List[KnowledgeItem]) -> None:
        """Add multiple knowledge items"""
        async with self._lock:
            self.knowledge_items.extend(items)
            self._knowledge_index = None  # Reset index

    async def add_action(
        self,
        action: str,
        details: Dict[str, Any],
        success: bool = True,
        duration: Optional[float] = None,
    ) -> None:
        """Record an action taken"""
        async with self._lock:
            entry = ActionDiaryEntry(
                iteration=self.iterations,
                action=action,
                details=details,
                success=success,
                duration_seconds=duration,
            )
            self.action_diary.append(entry)

    async def add_failed_attempt(
        self, action: str, error: str, context: Dict[str, Any]
    ) -> None:
        """Record a failed attempt for learning"""
        async with self._lock:
            self.failed_attempts.append(
                {
                    "iteration": self.iterations,
                    "action": action,
                    "error": error,
                    "context": context,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def get_relevant_knowledge(
        self,
        query: str,
        limit: int = 10,
        knowledge_types: Optional[List[KnowledgeType]] = None,
    ) -> List[KnowledgeItem]:
        """
        Get most relevant knowledge for a query.
        Simple implementation - could be enhanced with embeddings.
        """
        async with self._lock:
            filtered_items = list(self.knowledge_items)  # Create copy to work with

            # Filter by type if specified
            if knowledge_types:
                filtered_items = [
                    item
                    for item in filtered_items
                    if item.knowledge_type in knowledge_types
                ]

            # Sort by relevance score and recency
            sorted_items = sorted(
                filtered_items,
                key=lambda x: (x.relevance_score, x.confidence, -x.used_count),
                reverse=True,
            )

            # Return top items
            results = sorted_items[:limit]

            # Increment usage count
            for item in results:
                item.increment_usage()

            return results

    def get_failed_attempts_summary(self) -> str:
        """Get summary of failed attempts for context"""
        if not self.failed_attempts:
            return "No failed attempts recorded."

        summary_lines = ["Previous failed attempts:"]
        for attempt in self.failed_attempts[-5:]:  # Last 5
            summary_lines.append(
                f"- {attempt['action']} at iteration {attempt['iteration']}: {attempt['error']}"
            )

        return "\n".join(summary_lines)

    def estimate_context_size(self) -> int:
        """Estimate current context size in tokens (rough approximation)"""
        # Rough estimates: 1 token ≈ 4 characters
        total_chars = 0

        # Knowledge items
        for item in self.knowledge_items:
            total_chars += len(item.question) + len(item.answer)

        # Action diary
        for entry in self.action_diary:
            total_chars += len(json.dumps(entry.to_dict()))

        # Research history (synthesis messages)
        # This is harder to estimate without knowing message format
        total_chars += len(str(self.research_history))

        # Failed attempts
        total_chars += len(json.dumps(self.failed_attempts))

        self.context_tokens = total_chars // 4
        return self.context_tokens

    async def trim_to_token_limit(self, max_tokens: int) -> Tuple[int, int]:
        """
        Trim memory to fit within token limit.
        Returns (items_removed, tokens_saved).
        """
        async with self._lock:
            current_tokens = self.estimate_context_size()
            if current_tokens <= max_tokens:
                return 0, 0

            tokens_to_save = current_tokens - max_tokens
            items_removed = 0
            tokens_saved = 0

            # Remove oldest, least-used knowledge items first
            if self.knowledge_items:
                sorted_knowledge = sorted(
                    self.knowledge_items,
                    key=lambda x: (x.used_count, x.relevance_score, x.confidence),
                )

                while tokens_saved < tokens_to_save and sorted_knowledge:
                    item = sorted_knowledge.pop(0)
                    self.knowledge_items.remove(item)
                    items_removed += 1
                    # Rough estimate of tokens saved
                    tokens_saved += (len(item.question) + len(item.answer)) // 4

            # Trim old action diary entries if needed
            if tokens_saved < tokens_to_save and len(self.action_diary) > 10:
                entries_to_remove = min(len(self.action_diary) - 10, 10)
                self.action_diary = self.action_diary[entries_to_remove:]
                items_removed += entries_to_remove
                tokens_saved += entries_to_remove * 50  # Rough estimate

            return items_removed, tokens_saved


class KnowledgeExtractor:
    """Extracts structured knowledge from research findings"""

    def __init__(self, llm_factory, context=None):
        self.llm_factory = llm_factory
        self.logger = logger
        self.context = context

    async def extract_knowledge(
        self, result: SubagentResult, context: Dict[str, Any]
    ) -> List[KnowledgeItem]:
        """Extract structured knowledge from a subagent result"""
        if not result.success or not result.findings:
            return []

        extraction_prompt = f"""
<adaptive:knowledge-extraction>
    <adaptive:context>
        <adaptive:aspect>{result.aspect_name}</adaptive:aspect>
        <adaptive:objective>{context.get("objective", "Unknown")}</adaptive:objective>
    </adaptive:context>
    
    <adaptive:findings>
{result.findings}
    </adaptive:findings>
    
    <adaptive:task>
        Extract structured knowledge items from these findings.
        Each item should have:
        - A clear question it answers
        - A concise, factual answer
        - Confidence level (0-1)
        - Knowledge type: {", ".join([t.value for t in KnowledgeType])}
        
        Focus on extracting:
        1. Key facts and definitions
        2. Answers to specific questions
        3. Important limitations or caveats
        4. Useful resources or references
        5. Strategies or approaches discovered
        
        Be selective - only extract high-value, reusable knowledge.
    </adaptive:task>
</adaptive:knowledge-extraction>"""

        # Create extraction agent
        extractor = Agent(
            name="KnowledgeExtractor",
            instruction="Extract structured, reusable knowledge from research findings.",
            context=self.context,
        )

        llm = self.llm_factory(extractor)

        # Define response model
        from pydantic import BaseModel, Field

        class KnowledgeExtractionItem(BaseModel):
            question: str = Field(description="The question this knowledge answers")
            answer: str = Field(description="The concise answer")
            confidence: float = Field(ge=0.0, le=1.0, description="Confidence level")
            knowledge_type: KnowledgeType = Field(description="Type of knowledge")
            key_phrases: List[str] = Field(
                default_factory=list, description="Key phrases for indexing"
            )

        class KnowledgeExtractionResponse(BaseModel):
            items: List[KnowledgeExtractionItem] = Field(
                max_length=10, description="Extracted knowledge items"
            )
            summary: str = Field(description="Brief summary of what was extracted")

        try:
            response = await llm.generate_structured(
                message=extraction_prompt, response_model=KnowledgeExtractionResponse
            )

            # Convert to KnowledgeItem objects
            knowledge_items = []
            for item in response.items:
                knowledge_items.append(
                    KnowledgeItem(
                        question=item.question,
                        answer=item.answer,
                        confidence=item.confidence,
                        knowledge_type=item.knowledge_type,
                        sources=[result.aspect_name],
                        metadata={
                            "key_phrases": item.key_phrases,
                            "extraction_summary": response.summary,
                        },
                    )
                )

            self.logger.debug(
                f"Extracted {len(knowledge_items)} knowledge items from {result.aspect_name}"
            )
            return knowledge_items

        except Exception as e:
            self.logger.error(f"Failed to extract knowledge: {str(e)}")
            return []

    def format_knowledge_for_context(
        self, knowledge_items: List[KnowledgeItem], group_by_type: bool = True
    ) -> str:
        """Format knowledge items for inclusion in LLM context"""
        if not knowledge_items:
            return "No structured knowledge available."

        if group_by_type:
            # Group by knowledge type
            by_type: Dict[KnowledgeType, List[KnowledgeItem]] = {}
            for item in knowledge_items:
                if item.knowledge_type not in by_type:
                    by_type[item.knowledge_type] = []
                by_type[item.knowledge_type].append(item)

            # Format each type
            sections = []
            for k_type, items in by_type.items():
                # Properly pluralize the tag name
                tag_name = k_type.value
                if not tag_name.endswith("s"):
                    tag_name += "s"

                section_lines = [f"<adaptive:{tag_name}>"]
                for item in items:
                    section_lines.append(
                        f"  • Q: {item.question}\n    A: {item.answer} "
                        f"(confidence: {item.confidence:.2f}, used: {item.used_count}x)"
                    )
                section_lines.append(f"</adaptive:{tag_name}>")
                sections.append("\n".join(section_lines))

            return "\n\n".join(sections)
        else:
            # Simple list format
            lines = ["<adaptive:knowledge-base>"]
            for item in knowledge_items:
                lines.append(
                    f"  [{item.knowledge_type.value}] {item.question}\n"
                    f"  → {item.answer} (confidence: {item.confidence:.2f})"
                )
            lines.append("</adaptive:knowledge-base>")
            return "\n".join(lines)
