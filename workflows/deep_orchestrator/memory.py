"""
Memory system for the Deep Orchestrator workflow.

This module provides enhanced memory management with knowledge extraction,
context management, and filesystem workspace support.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.models import KnowledgeItem, TaskResult

logger = get_logger(__name__)


class WorkspaceMemory:
    """
    Enhanced memory system with knowledge extraction and context management.

    This class manages in-memory and optional filesystem storage of artifacts,
    knowledge items, and task results. It provides context management to prevent
    token overflow and knowledge indexing for fast retrieval.
    """

    def __init__(
        self,
        use_filesystem: bool = True,
        workspace_dir: Path = Path(".adaptive_workspace"),
    ):
        """
        Initialize the workspace memory.

        Args:
            use_filesystem: Whether to enable filesystem storage
            workspace_dir: Directory for filesystem workspace
        """
        self.use_filesystem = use_filesystem
        self.workspace_dir = workspace_dir

        # In-memory storage
        self.artifacts: Dict[str, str] = {}
        self.knowledge: List[KnowledgeItem] = []
        self.task_results: List[TaskResult] = []
        self.metadata: Dict[str, Any] = {}

        # Knowledge index for fast retrieval
        self.knowledge_by_category: Dict[str, List[KnowledgeItem]] = defaultdict(list)

        # Create filesystem workspace if enabled
        if self.use_filesystem:
            self.workspace_dir.mkdir(exist_ok=True)
            (self.workspace_dir / "scratchpad").mkdir(exist_ok=True)
            (self.workspace_dir / "artifacts").mkdir(exist_ok=True)

        logger.info(
            f"Initialized WorkspaceMemory (filesystem="
            f"{'enabled' if use_filesystem else 'disabled'})"
        )

    def save_artifact(
        self, name: str, content: str, to_filesystem: bool = False
    ) -> None:
        """
        Save an artifact to memory and optionally to filesystem.

        Args:
            name: Name of the artifact
            content: Content to save
            to_filesystem: Whether to also save to filesystem
        """
        self.artifacts[name] = content
        logger.debug(f"Saved artifact '{name}' ({len(content)} chars)")

        if to_filesystem and self.use_filesystem:
            artifact_path = self.workspace_dir / "artifacts" / name
            with open(artifact_path, "w") as f:
                f.write(content)
            logger.debug(f"Also saved artifact '{name}' to filesystem")

    def get_artifact(self, name: str) -> Optional[str]:
        """
        Get an artifact by name.

        Args:
            name: Name of the artifact

        Returns:
            Artifact content if found, None otherwise
        """
        return self.artifacts.get(name)

    def add_knowledge(self, item: KnowledgeItem) -> None:
        """
        Add a knowledge item with indexing.

        Args:
            item: Knowledge item to add
        """
        self.knowledge.append(item)
        self.knowledge_by_category[item.category].append(item)
        logger.debug(
            f"Added knowledge: {item.key} (category: {item.category}, "
            f"confidence: {item.confidence:.2f})"
        )

    def get_relevant_knowledge(
        self, query: str, limit: int = 10
    ) -> List[KnowledgeItem]:
        """
        Get most relevant knowledge items for a query.

        Simple relevance based on recency, confidence, and keyword overlap.
        In production, this would use embeddings for better similarity matching.

        Args:
            query: Query string to match against
            limit: Maximum number of items to return

        Returns:
            List of relevant knowledge items
        """
        # Sort by confidence and recency
        sorted_knowledge = sorted(
            self.knowledge,
            key=lambda k: (k.confidence, k.timestamp.timestamp()),
            reverse=True,
        )

        # Filter by query keywords (simple approach)
        query_words = set(query.lower().split())
        relevant = []

        for item in sorted_knowledge:
            item_words = set(item.key.lower().split()) | set(
                str(item.value).lower().split()[:20]
            )
            if query_words & item_words:  # Any overlap
                relevant.append(item)
                if len(relevant) >= limit:
                    break

        # Fill with high-confidence items if needed
        if len(relevant) < limit:
            for item in sorted_knowledge:
                if item not in relevant:
                    relevant.append(item)
                    if len(relevant) >= limit:
                        break

        return relevant

    def get_knowledge_summary(self, limit: int = 10) -> str:
        """
        Get a formatted XML summary of recent knowledge.

        Args:
            limit: Maximum number of items to include

        Returns:
            XML-formatted knowledge summary
        """
        if not self.knowledge:
            return "No knowledge accumulated yet."

        recent = sorted(self.knowledge, key=lambda k: k.timestamp, reverse=True)[:limit]
        lines = ["<knowledge_summary>"]

        # Group by category
        by_category = defaultdict(list)
        for item in recent:
            by_category[item.category].append(item)

        for category, items in by_category.items():
            lines.append(f'  <category name="{category}">')
            for item in items:
                value_str = str(item.value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                lines.append(
                    f'    <item confidence="{item.confidence:.2f}" '
                    f'source="{item.source}">'
                )
                lines.append(f"      <key>{item.key}</key>")
                lines.append(f"      <value>{value_str}</value>")
                lines.append("    </item>")
            lines.append("  </category>")

        lines.append("</knowledge_summary>")
        return "\n".join(lines)

    def add_task_result(self, result: TaskResult) -> None:
        """
        Record a task result and extract artifacts/knowledge.

        Args:
            result: Task result to record
        """
        self.task_results.append(result)

        # Save artifacts
        for name, content in result.artifacts.items():
            self.save_artifact(name, content)

        # Add knowledge
        for item in result.knowledge_extracted:
            self.add_knowledge(item)

        logger.info(
            f"Recorded task result: {result.task_name} "
            f"(status: {result.status}, duration: {result.duration_seconds:.1f}s, "
            f"artifacts: {len(result.artifacts)}, "
            f"knowledge: {len(result.knowledge_extracted)})"
        )

    def estimate_context_size(self) -> int:
        """
        Estimate total context size in tokens.

        Uses rough heuristic: 1 token ≈ 4 characters

        Returns:
            Estimated token count
        """
        total_chars = 0

        # Knowledge items
        for item in self.knowledge:
            total_chars += len(item.key) + len(str(item.value))

        # Artifacts (limited to prevent overflow)
        for name, content in list(self.artifacts.items())[:10]:
            total_chars += len(name) + min(len(content), 1000)

        # Task results
        for result in self.task_results[-20:]:  # Last 20
            if result.output:
                total_chars += min(len(result.output), 500)

        return total_chars // 4

    def trim_for_context(self, max_tokens: int = 50000) -> int:
        """
        Trim memory to fit within context window.

        Removes oldest, lowest confidence items first.

        Args:
            max_tokens: Maximum token limit

        Returns:
            Number of items removed
        """
        current_estimate = self.estimate_context_size()
        if current_estimate <= max_tokens:
            return 0

        items_removed = 0

        # Remove oldest, lowest confidence knowledge
        if len(self.knowledge) > 20:
            sorted_knowledge = sorted(
                self.knowledge, key=lambda k: (k.confidence, k.timestamp.timestamp())
            )
            to_remove = len(self.knowledge) - 20
            self.knowledge = sorted_knowledge[to_remove:]
            items_removed += to_remove

            # Rebuild category index
            self.knowledge_by_category.clear()
            for item in self.knowledge:
                self.knowledge_by_category[item.category].append(item)

        # Trim old task results
        if len(self.task_results) > 10:
            removed = len(self.task_results) - 10
            self.task_results = self.task_results[-10:]
            items_removed += removed

        logger.info(f"Trimmed memory: removed {items_removed} items to fit context")
        return items_removed

    def get_scratchpad_path(self) -> Optional[Path]:
        """
        Get the scratchpad directory path if filesystem is enabled.

        Returns:
            Path to scratchpad directory or None
        """
        if self.use_filesystem:
            return self.workspace_dir / "scratchpad"
        return None

    def clear(self) -> None:
        """Clear all memory."""
        self.artifacts.clear()
        self.knowledge.clear()
        self.task_results.clear()
        self.metadata.clear()
        self.knowledge_by_category.clear()
        logger.info("Memory cleared")

    def get_stats(self) -> Dict[str, int]:
        """
        Get memory statistics.

        Returns:
            Dictionary with counts of various memory items
        """
        return {
            "artifacts": len(self.artifacts),
            "knowledge_items": len(self.knowledge),
            "task_results": len(self.task_results),
            "knowledge_categories": len(self.knowledge_by_category),
            "estimated_tokens": self.estimate_context_size(),
        }
