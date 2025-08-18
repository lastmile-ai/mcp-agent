"""
Context building utilities for the Deep Orchestrator workflow.

This module handles building task execution contexts with intelligent
token management, relevance scoring, and compression.
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.memory import WorkspaceMemory
from mcp_agent.workflows.deep_orchestrator.models import KnowledgeItem, Task, TaskResult
from mcp_agent.workflows.deep_orchestrator.prompts import get_task_context

if TYPE_CHECKING:
    from mcp_agent.workflows.deep_orchestrator.queue import TodoQueue

logger = get_logger(__name__)


class ContextBuilder:
    """Builds execution contexts for tasks with smart token management."""

    def __init__(
        self,
        objective: str,
        memory: WorkspaceMemory,
        queue: "TodoQueue",
        task_context_budget: int = 50000,
        context_relevance_threshold: float = 0.7,
        context_compression_ratio: float = 0.8,
        enable_full_context_propagation: bool = True,
    ):
        """
        Initialize the context builder.

        Args:
            objective: The main objective being worked on
            memory: Workspace memory for knowledge and artifacts
            queue: Task queue for finding task results
            task_context_budget: Maximum tokens for task context
            context_relevance_threshold: Minimum relevance score to include context
            context_compression_ratio: When to start compressing context
            enable_full_context_propagation: Whether to propagate full context to tasks
        """
        self.objective = objective
        self.memory = memory
        self.queue = queue
        self.task_context_budget = task_context_budget
        self.context_relevance_threshold = context_relevance_threshold
        self.context_compression_ratio = context_compression_ratio
        self.enable_full_context_propagation = enable_full_context_propagation

        # Track context usage statistics
        self.context_usage_stats = {
            "tasks_with_full_context": 0,
            "tasks_with_compressed_context": 0,
            "total_context_tokens": 0,
        }

    def build_task_context(self, task: Task) -> str:
        """
        Build context for task execution based on task requirements.

        Automatically selects the appropriate context building strategy:
        - Explicit dependencies if specified
        - Full context if enabled
        - Basic context otherwise

        Args:
            task: Task to build context for

        Returns:
            Task context string
        """
        if task.requires_context_from:
            # Use explicit dependencies if specified
            return self.build_relevant_task_context(task)
        elif self.enable_full_context_propagation:
            return self.build_full_task_context(task)
        else:
            return self.build_basic_task_context(task)

    def build_basic_task_context(self, task: Task) -> str:
        """
        Build basic context for task execution.

        Includes only relevant knowledge and available artifacts.

        Args:
            task: Task to build context for

        Returns:
            Basic task context string
        """
        # Get relevant knowledge
        relevant_knowledge = self.memory.get_relevant_knowledge(
            task.description, limit=5
        )

        # Convert to dict format
        knowledge_items = [
            {"key": item.key, "value": item.value, "confidence": item.confidence}
            for item in relevant_knowledge
        ]

        # Get available artifacts
        artifact_names = (
            list(self.memory.artifacts.keys())[-5:] if self.memory.artifacts else None
        )

        # Get scratchpad path
        scratchpad_path = (
            str(self.memory.get_scratchpad_path())
            if self.memory.get_scratchpad_path()
            else None
        )

        return get_task_context(
            objective=self.objective,
            task_description=task.description,
            relevant_knowledge=knowledge_items,
            available_artifacts=artifact_names,
            scratchpad_path=scratchpad_path,
            required_servers=task.servers,
        )

    def build_full_task_context(self, task: Task) -> str:
        """
        Build comprehensive context with all prior task results.

        Includes smart token management and relevance-based prioritization.

        Args:
            task: Task to build context for

        Returns:
            Full task context string
        """
        # Start with essential context
        essential_parts = [
            f"<objective>{self.objective}</objective>",
            f"<task>{task.description}</task>",
        ]

        # Estimate tokens for essential parts
        essential_tokens = self._estimate_tokens("\n".join(essential_parts))
        remaining_budget = self.task_context_budget - essential_tokens

        # Gather all available context sources with relevance scores
        context_sources = self._gather_context_sources(task)

        # Sort by relevance and recency
        context_sources.sort(
            key=lambda x: (x["relevance"], x["timestamp"]), reverse=True
        )

        # Build context within budget
        context_parts = essential_parts.copy()

        if self.enable_full_context_propagation and remaining_budget > 0:
            context_parts.append("<previous_task_results>")

            added_sources = []
            current_tokens = essential_tokens

            for source in context_sources:
                source_tokens = source["estimated_tokens"]

                # Check if we can fit this source
                if current_tokens + source_tokens <= self.task_context_budget:
                    context_parts.append(source["content"])
                    added_sources.append(source["id"])
                    current_tokens += source_tokens
                else:
                    # Try compression if we're close to the limit
                    if (
                        current_tokens / self.task_context_budget
                        >= self.context_compression_ratio
                    ):
                        compressed = self._compress_context_source(source)
                        compressed_tokens = compressed["estimated_tokens"]

                        if (
                            current_tokens + compressed_tokens
                            <= self.task_context_budget
                        ):
                            context_parts.append(compressed["content"])
                            added_sources.append(f"{source['id']}_compressed")
                            current_tokens += compressed_tokens
                            self.context_usage_stats[
                                "tasks_with_compressed_context"
                            ] += 1

            context_parts.append("</previous_task_results>")

            # Log context usage
            logger.debug(
                f"Task context built: {current_tokens}/{self.task_context_budget} tokens, "
                f"{len(added_sources)} sources included"
            )
            self.context_usage_stats["total_context_tokens"] += current_tokens

            if len(added_sources) == len(context_sources):
                self.context_usage_stats["tasks_with_full_context"] += 1

        # Always add relevant knowledge (compact representation)
        knowledge_budget = min(
            5000, remaining_budget // 4
        )  # Reserve some space for knowledge
        relevant_knowledge = self._get_prioritized_knowledge(task, knowledge_budget)

        if relevant_knowledge:
            context_parts.append("<relevant_knowledge>")
            for item in relevant_knowledge:
                context_parts.append(
                    f'  <knowledge confidence="{item.confidence:.2f}" category="{item.category}">'
                )
                context_parts.append(f"    <insight>{item.key}: {item.value}</insight>")
                context_parts.append("  </knowledge>")
            context_parts.append("</relevant_knowledge>")

        # Add tool requirements
        if task.servers:
            context_parts.append("<required_tools>")
            for server in task.servers:
                context_parts.append(f"  <tool>{server}</tool>")
            context_parts.append("</required_tools>")

        # Add any existing artifacts
        if self.memory.artifacts:
            context_parts.append("<available_artifacts>")
            for name in list(self.memory.artifacts.keys())[-5:]:  # Last 5 artifacts
                context_parts.append(f"  <artifact>{name}</artifact>")
            context_parts.append("</available_artifacts>")

        return "\n".join(context_parts)

    def build_relevant_task_context(self, task: Task) -> str:
        """
        Build task context with explicitly requested dependencies.

        Uses the task's requires_context_from field to include
        only the outputs from specifically requested previous tasks.

        Args:
            task: Task to build context for

        Returns:
            Task context string with requested dependencies
        """
        # Start with essential context
        essential_parts = [
            f"<objective>{self.objective}</objective>",
            f"<task>{task.description}</task>",
        ]

        # Track tokens for budget management
        essential_tokens = self._estimate_tokens("\n".join(essential_parts))
        budget = task.context_window_budget
        remaining_budget = budget - essential_tokens

        # Build context parts
        context_parts = essential_parts.copy()
        current_tokens = essential_tokens

        # Add requested task outputs
        if task.requires_context_from and remaining_budget > 0:
            context_parts.append("<required_context>")

            # Gather requested task results as context sources
            requested_sources = []
            for task_name in task.requires_context_from:
                # Find the task by name
                referenced_task = self.queue.get_task_by_name(task_name)
                if not referenced_task:
                    logger.warning(
                        f"Task '{task.name}' requested context from unknown task '{task_name}'"
                    )
                    continue

                # Find the result for this task
                result = self._find_task_result_by_name(referenced_task.name)
                if not result:
                    logger.warning(f"No result found for task '{task_name}'")
                    continue

                if not result.success or not result.output:
                    logger.warning(f"Task '{task_name}' failed or has no output")
                    continue

                # Get the step description for this task
                step_description = self._find_step_for_task(referenced_task.name)

                # Format using existing method
                content = self._format_task_result_for_context(
                    step_description=step_description or "Unknown Step",
                    task=referenced_task,
                    result=result,
                )

                requested_sources.append(
                    {
                        "id": f"task_{referenced_task.name}",
                        "name": task_name,
                        "type": "requested_dependency",
                        "relevance": 1.0,  # Explicitly requested, so max relevance
                        "content": content,
                        "estimated_tokens": self._estimate_tokens(content),
                        "original_result": result,
                    }
                )

            # Sort by order in requires_context_from to maintain priority
            ordered_sources = []
            for task_name in task.requires_context_from:
                for source in requested_sources:
                    if source["name"] == task_name:
                        ordered_sources.append(source)
                        break

            # Add sources within budget
            for source in ordered_sources:
                source_tokens = source["estimated_tokens"]

                if current_tokens + source_tokens <= budget:
                    context_parts.append(source["content"])
                    current_tokens += source_tokens
                else:
                    # Try compression
                    compressed = self._compress_context_source(source)
                    compressed_tokens = compressed["estimated_tokens"]

                    if current_tokens + compressed_tokens <= budget:
                        context_parts.append(compressed["content"])
                        current_tokens += compressed_tokens
                        logger.info(
                            f"Compressed output for task '{source['name']}' to fit budget"
                        )
                    else:
                        logger.warning(
                            f"Cannot fit task '{source['name']}' in context even with compression "
                            f"(needs {compressed_tokens} tokens, only {budget - current_tokens} available)"
                        )

            context_parts.append("</required_context>")

        # Add relevant knowledge using existing method
        knowledge_budget = min(5000, remaining_budget // 4)
        relevant_knowledge = self._get_prioritized_knowledge(task, knowledge_budget)

        if relevant_knowledge:
            context_parts.append("<relevant_knowledge>")
            for item in relevant_knowledge:
                context_parts.append(
                    f'  <knowledge confidence="{item.confidence:.2f}" category="{item.category}" source="{item.source}">'
                )
                context_parts.append(f"    <insight>{item.key}: {item.value}</insight>")
                context_parts.append("  </knowledge>")
            context_parts.append("</relevant_knowledge>")

        # Add tool requirements
        if task.servers:
            context_parts.append("<required_tools>")
            for server in task.servers:
                context_parts.append(f"  <tool>{server}</tool>")
            context_parts.append("</required_tools>")

        # Add available artifacts (let the method decide how many based on space)
        if self.memory.artifacts and current_tokens < budget - 1000:
            context_parts.append("<available_artifacts>")
            artifacts_added = 0
            for name in reversed(list(self.memory.artifacts.keys())):
                artifact_line = f"  <artifact>{name}</artifact>"
                artifact_tokens = self._estimate_tokens(artifact_line)
                if current_tokens + artifact_tokens < budget - 500:  # Leave some buffer
                    context_parts.append(artifact_line)
                    current_tokens += artifact_tokens
                    artifacts_added += 1
                    if artifacts_added >= 5:  # Reasonable limit
                        break
            context_parts.append("</available_artifacts>")

        # Add scratchpad path if available
        scratchpad_path = self.memory.get_scratchpad_path()
        if scratchpad_path:
            context_parts.append(
                f"<scratchpad_path>{scratchpad_path}</scratchpad_path>"
            )

        final_context = "\n".join(context_parts)
        final_tokens = self._estimate_tokens(final_context)

        logger.debug(
            f"Built relevant context for task '{task.name}': "
            f"{len(task.requires_context_from)} dependencies requested, "
            f"{final_tokens} tokens used (budget: {budget})"
        )

        return final_context

    def get_context_usage_stats(self) -> Dict[str, Any]:
        """Get statistics about context usage."""
        total_tasks = (
            self.context_usage_stats["tasks_with_full_context"]
            + self.context_usage_stats["tasks_with_compressed_context"]
        )

        stats = {
            "tasks_with_full_context": self.context_usage_stats[
                "tasks_with_full_context"
            ],
            "tasks_with_compressed_context": self.context_usage_stats[
                "tasks_with_compressed_context"
            ],
            "total_tasks_with_context": total_tasks,
            "average_context_tokens": self.context_usage_stats["total_context_tokens"]
            / total_tasks
            if total_tasks > 0
            else 0,
            "total_context_tokens": self.context_usage_stats["total_context_tokens"],
            "context_propagation_enabled": self.enable_full_context_propagation,
            "context_budget": self.task_context_budget,
        }

        return stats

    # Helper methods (these don't modify class state, so they can be static or take parameters)

    def _gather_context_sources(self, task: Task) -> List[Dict[str, Any]]:
        """Gather all potential context sources with relevance scoring."""
        sources = []

        # Get all completed task results
        for step in self.queue.completed_steps:
            for step_task in step.tasks:
                result = self._find_task_result_by_name(step_task.name)
                if result and result.success and result.output:
                    # Calculate relevance score
                    relevance = self._calculate_relevance(
                        task_description=task.description,
                        source_task_description=step_task.description,
                        source_output=result.output,
                        source_step=step.description,
                    )

                    # Format the source content
                    content = self._format_task_result_for_context(
                        step_description=step.description, task=step_task, result=result
                    )

                    sources.append(
                        {
                            "id": f"task_{step_task.name}",
                            "type": "task_result",
                            "relevance": relevance,
                            "timestamp": result.duration_seconds,  # Use as proxy for recency
                            "content": content,
                            "estimated_tokens": self._estimate_tokens(content),
                            "original_result": result,
                        }
                    )

        return sources

    def _find_task_result_by_name(self, task_name: str) -> Optional[TaskResult]:
        """Find a task result by task name."""
        for result in self.memory.task_results:
            if result.task_name == task_name:
                return result
        return None

    def _find_step_for_task(self, task_name: str) -> Optional[str]:
        """Find the step description that contains a task."""
        for step in self.queue.completed_steps:
            for task in step.tasks:
                if task.name == task_name:
                    return step.description
        return None

    def _calculate_relevance(
        self,
        task_description: str,
        source_task_description: str,
        source_output: str,
        source_step: str,
    ) -> float:
        """Calculate relevance score between current task and a source."""

        # Simple keyword-based relevance (can be enhanced with embeddings)
        task_words = set(task_description.lower().split())
        source_words = set(source_task_description.lower().split())
        output_words = set(source_output.lower().split()[:100])  # First 100 words
        step_words = set(source_step.lower().split())

        # Check for explicit references
        if any(
            ref in task_description.lower()
            for ref in ["previous", "all", "comprehensive", "synthesize", "compile"]
        ):
            base_relevance = 0.8
        else:
            base_relevance = 0.5

        # Calculate word overlap
        task_overlap = (
            len(task_words & source_words) / len(task_words) if task_words else 0
        )
        output_overlap = (
            len(task_words & output_words) / len(task_words) if task_words else 0
        )
        step_overlap = (
            len(task_words & step_words) / len(task_words) if task_words else 0
        )

        # Weighted relevance
        relevance = (
            base_relevance * 0.4
            + task_overlap * 0.3
            + output_overlap * 0.2
            + step_overlap * 0.1
        )

        # Boost relevance for certain patterns
        if (
            "report" in task_description.lower()
            and "analysis" in source_task_description.lower()
        ):
            relevance = min(1.0, relevance + 0.2)

        return min(1.0, relevance)

    def _format_task_result_for_context(
        self, step_description: str, task: Task, result: TaskResult
    ) -> str:
        """Format a task result for inclusion in context."""
        parts = [
            f'  <step_result step="{step_description}">',
            f'    <task name="{task.name}">{task.description}</task>',
            f"    <output>{result.output}</output>",
        ]

        # Include key knowledge if available
        if result.knowledge_extracted:
            parts.append("    <key_findings>")
            for item in result.knowledge_extracted[:5]:  # Top 5 findings
                parts.append(f"      - {item.key}: {item.value}")
            parts.append("    </key_findings>")

        parts.append("  </step_result>")
        return "\n".join(parts)

    def _compress_context_source(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Compress a context source to fit within budget."""
        result = source["original_result"]

        # Simple compression: truncate output and keep only key findings
        compressed_output = (
            result.output[:500] + "..." if len(result.output) > 500 else result.output
        )

        parts = [
            f'  <step_result_compressed step="{source["id"]}">',
            f"    <summary>{compressed_output}</summary>",
        ]

        if result.knowledge_extracted:
            parts.append("    <key_findings>")
            for item in result.knowledge_extracted[:3]:  # Even fewer findings
                parts.append(f"      - {item.key}")
            parts.append("    </key_findings>")

        parts.append("  </step_result_compressed>")

        content = "\n".join(parts)

        return {
            "id": source["id"],
            "content": content,
            "estimated_tokens": self._estimate_tokens(content),
        }

    def _get_prioritized_knowledge(
        self, task: Task, token_budget: int
    ) -> List[KnowledgeItem]:
        """Get knowledge items prioritized by relevance within token budget."""
        if not self.memory.knowledge:
            return []

        # Score all knowledge items
        scored_items = []
        for item in self.memory.knowledge:
            relevance = self._calculate_knowledge_relevance(task.description, item)
            if relevance >= self.context_relevance_threshold:
                scored_items.append((relevance, item))

        # Sort by relevance and recency
        scored_items.sort(
            key=lambda x: (x[0], x[1].timestamp.timestamp()), reverse=True
        )

        # Select items within budget
        selected = []
        current_tokens = 0

        for relevance, item in scored_items:
            item_tokens = self._estimate_tokens(f"{item.key}: {item.value}")
            if current_tokens + item_tokens <= token_budget:
                selected.append(item)
                current_tokens += item_tokens
            else:
                break

        return selected

    def _calculate_knowledge_relevance(
        self, task_description: str, item: KnowledgeItem
    ) -> float:
        """Calculate relevance of a knowledge item to a task."""
        # Simple implementation - can be enhanced
        task_words = set(task_description.lower().split())
        item_words = set(item.key.lower().split()) | set(
            str(item.value).lower().split()[:20]
        )

        overlap = len(task_words & item_words) / len(task_words) if task_words else 0

        # Boost by confidence and category relevance
        category_boost = (
            0.2 if item.category in ["findings", "analysis", "errors"] else 0
        )

        return min(1.0, overlap + category_boost) * item.confidence

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Simple heuristic: 1 token ≈ 4 characters
        # Can be replaced with actual tokenizer
        return len(text) // 4
