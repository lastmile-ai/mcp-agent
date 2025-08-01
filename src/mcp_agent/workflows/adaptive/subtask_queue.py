"""
Subtask Queue Management for AdaptiveWorkflow
Based on DeepSearch FIFO pattern with enhancements for research aspects
"""

import asyncio
from collections import deque
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
import numpy as np

from mcp_agent.workflows.adaptive.models import ResearchAspect, TaskType


@dataclass
class SubtaskQueueItem:
    """Enhanced research aspect with queue metadata"""

    aspect: ResearchAspect
    parent_objective: str
    depth: int = 0  # How deep in the subtask tree
    priority: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 0
    last_error: Optional[str] = None

    def __repr__(self) -> str:
        return f"SubtaskQueueItem(name={self.aspect.name}, depth={self.depth}, attempts={self.attempt_count})"


class AdaptiveSubtaskQueue:
    """
    FIFO queue for managing research subtasks with rotation.
    Ensures original objective is revisited with accumulated knowledge.
    """

    def __init__(
        self, original_objective: str, task_type: TaskType, max_attempts: int = 3
    ):
        self.original_objective = original_objective
        self.task_type = task_type
        self.max_attempts = max_attempts
        self.queue: deque[SubtaskQueueItem] = deque()
        self.completed_subtasks: List[SubtaskQueueItem] = []
        self.failed_subtasks: List[SubtaskQueueItem] = []
        self.seen_objectives: Set[str] = set()
        self._lock = asyncio.Lock()

        # Add original objective as first item
        original_aspect = ResearchAspect(
            name="Original Objective", objective=original_objective, required_servers=[]
        )
        self.queue.append(
            SubtaskQueueItem(
                aspect=original_aspect,
                parent_objective=original_objective,
                depth=0,
                priority=1.0,
            )
        )
        self.seen_objectives.add(original_objective)

    async def add_subtasks(
        self, new_aspects: List[ResearchAspect], parent_objective: str, depth: int
    ) -> int:
        """
        Add new subtasks based on identified aspects.
        New subtasks go to front, original objective rotates to back.
        Returns number of subtasks actually added (after deduplication).
        """
        async with self._lock:
            added_count = 0

            # Check if we're adding subtasks to the original objective
            is_original_parent = (
                parent_objective == self.original_objective and depth == 0
            )

            # Add new aspects to front of queue
            for aspect in new_aspects:
                # Simple deduplication based on objective text
                if aspect.objective not in self.seen_objectives:
                    item = SubtaskQueueItem(
                        aspect=aspect,
                        parent_objective=parent_objective,
                        depth=depth + 1,
                        priority=1.0 / (depth + 2),  # Deeper = lower priority
                    )
                    self.queue.appendleft(item)
                    self.seen_objectives.add(aspect.objective)
                    added_count += 1

            # If we added subtasks to the original objective, re-add it to the back
            if added_count > 0 and is_original_parent:
                # Re-add original objective to back of queue for later revisiting
                original_aspect = ResearchAspect(
                    name="Original Objective",
                    objective=self.original_objective,
                    required_servers=[],
                )
                original_item = SubtaskQueueItem(
                    aspect=original_aspect,
                    parent_objective=self.original_objective,
                    depth=0,
                    priority=1.0,
                )
                self.queue.append(original_item)

            return added_count

    async def get_next(self) -> Optional[SubtaskQueueItem]:
        """Get next subtask from queue"""
        async with self._lock:
            if self.queue:
                item = self.queue.popleft()
                return item
            return None

    async def requeue_failed(self, item: SubtaskQueueItem) -> bool:
        """
        Requeue a failed subtask if it hasn't exceeded max attempts.
        Returns True if requeued, False if moved to failed list.
        """
        async with self._lock:
            item.attempt_count += 1

            if item.attempt_count < self.max_attempts:
                # Add to back of queue with reduced priority
                item.priority *= 0.5
                self.queue.append(item)
                return True
            else:
                # Move to failed list
                self.failed_subtasks.append(item)
                return False

    async def mark_completed(self, item: SubtaskQueueItem) -> None:
        """Mark a subtask as completed"""
        async with self._lock:
            self.completed_subtasks.append(item)

    def has_next(self) -> bool:
        """Check if there are subtasks in queue"""
        return len(self.queue) > 0

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status for logging"""
        return {
            "queue_length": len(self.queue),
            "completed_count": len(self.completed_subtasks),
            "failed_count": len(self.failed_subtasks),
            "next_subtasks": [
                {"name": item.aspect.name, "depth": item.depth}
                for item in list(self.queue)[:3]
            ],
            "depth_distribution": self._get_depth_distribution(),
        }

    def _get_depth_distribution(self) -> Dict[int, int]:
        """Get distribution of subtasks by depth"""
        distribution = {}
        for item in self.queue:
            distribution[item.depth] = distribution.get(item.depth, 0) + 1
        return distribution

    def deduplicate_with_embeddings(
        self, embeddings_model, threshold: float = 0.85
    ) -> int:
        """
        Remove duplicate subtasks using semantic similarity.
        Returns number of duplicates removed.
        """
        if len(self.queue) < 2:
            return 0

        # Extract objectives for embedding
        items = list(self.queue)
        objectives = [item.aspect.objective for item in items]

        # Get embeddings
        embeddings = embeddings_model.encode(objectives)

        # Find duplicates using cosine similarity
        duplicates = set()
        for i in range(len(objectives)):
            if i in duplicates:
                continue
            for j in range(i + 1, len(objectives)):
                if j in duplicates:
                    continue

                # Calculate cosine similarity with division-by-zero protection
                norm_i = np.linalg.norm(embeddings[i])
                norm_j = np.linalg.norm(embeddings[j])

                # Protect against zero-vector embeddings
                if norm_i < 1e-9 or norm_j < 1e-9:
                    similarity = 0.0
                else:
                    similarity = np.dot(embeddings[i], embeddings[j]) / (
                        norm_i * norm_j
                    )

                if similarity > threshold:
                    # Keep the one with higher priority (lower depth)
                    if items[i].depth <= items[j].depth:
                        duplicates.add(j)
                    else:
                        duplicates.add(i)
                        break

        # Rebuild queue without duplicates
        self.queue.clear()
        removed_count = 0

        for i, item in enumerate(items):
            if i not in duplicates:
                self.queue.append(item)
            else:
                removed_count += 1
                # Remove from seen objectives to allow re-adding if needed
                self.seen_objectives.discard(item.aspect.objective)

        return removed_count

    def get_failed_summary(self) -> str:
        """Get summary of failed subtasks for context"""
        if not self.failed_subtasks:
            return "No failed subtasks."

        summary = "Failed subtasks:\n"
        for item in self.failed_subtasks[-5:]:  # Last 5 failures
            summary += f"- {item.aspect.name}: {item.last_error or 'Unknown error'}\n"

        return summary

    def estimate_remaining_work(self) -> Dict[str, Any]:
        """Estimate remaining work based on queue state"""
        total_items = len(self.queue)
        avg_depth = (
            sum(item.depth for item in self.queue) / total_items
            if total_items > 0
            else 0
        )

        # Estimate based on historical completion rate
        completion_rate = len(self.completed_subtasks) / (
            len(self.completed_subtasks) + len(self.failed_subtasks) + 1
        )

        return {
            "remaining_subtasks": total_items,
            "average_depth": avg_depth,
            "max_depth": max((item.depth for item in self.queue), default=0),
            "estimated_completion_rate": completion_rate,
            "has_original_objective": any(item.depth == 0 for item in self.queue),
        }
