"""
Knowledge extraction for the Deep Orchestrator workflow.

This module handles extraction of structured knowledge from task outputs
to build a reusable knowledge base during execution.
"""

from typing import Callable, List, Optional, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.models import (
    ExtractedKnowledge,
    KnowledgeItem,
    TaskResult,
)
from mcp_agent.workflows.deep_orchestrator.prompts import (
    KNOWLEDGE_EXTRACTOR_INSTRUCTION,
    get_extraction_prompt,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class KnowledgeExtractor:
    """Extract structured knowledge from task outputs."""

    def __init__(
        self,
        llm_factory: Callable[[Agent], AugmentedLLM],
        context: Optional["Context"] = None,
    ):
        """
        Initialize the knowledge extractor.

        Args:
            llm_factory: Factory function to create LLMs
            context: Application context
        """
        self.llm_factory = llm_factory
        self.context = context

    async def extract_knowledge(
        self, task_result: TaskResult, objective: str
    ) -> List[KnowledgeItem]:
        """
        Extract structured knowledge from a task result.

        Args:
            task_result: Result from task execution
            objective: Original objective for context

        Returns:
            List of extracted knowledge items
        """
        # Skip extraction for failed tasks or very short outputs
        if not task_result.success or not task_result.output:
            return []

        if len(task_result.output) < 50:
            logger.debug(
                f"Skipping knowledge extraction for task {task_result.task_name} "
                f"(output too short: {len(task_result.output)} chars)"
            )
            return []

        # Create extractor agent
        extractor = Agent(
            name="KnowledgeExtractor",
            instruction=KNOWLEDGE_EXTRACTOR_INSTRUCTION,
            context=self.context,
        )

        llm = self.llm_factory(extractor)

        # Build extraction prompt
        extraction_prompt = get_extraction_prompt(objective, task_result.output)

        try:
            # Extract knowledge using structured output
            response = await llm.generate_structured(
                message=extraction_prompt,
                response_model=ExtractedKnowledge,
                request_params=RequestParams(temperature=0.3, max_iterations=1),
            )

            # Convert to KnowledgeItem objects
            knowledge_items = []
            for item in response.items:
                # Parse confidence as float, handling string inputs
                confidence_raw = item.get("confidence", 0.8)
                if isinstance(confidence_raw, str):
                    try:
                        confidence = float(confidence_raw)
                    except (ValueError, TypeError):
                        confidence = 0.8
                elif isinstance(confidence_raw, (int, float)):
                    confidence = float(confidence_raw)
                else:
                    confidence = 0.8

                knowledge_items.append(
                    KnowledgeItem(
                        key=item.get("key", "Unknown"),
                        value=item.get("value", ""),
                        source=task_result.task_name,
                        confidence=confidence,
                        category=item.get("category", "general"),
                    )
                )

            logger.debug(
                f"Extracted {len(knowledge_items)} knowledge items from "
                f"task {task_result.task_name}"
            )
            return knowledge_items

        except Exception as e:
            logger.warning(f"Knowledge extraction failed: {e}")

            # Fallback to simple extraction
            return [
                KnowledgeItem(
                    key="Task output summary",
                    value=task_result.output[:200] + "..."
                    if len(task_result.output) > 200
                    else task_result.output,
                    source=task_result.task_name,
                    confidence=0.6,
                    category="summary",
                )
            ]

    async def extract_batch(
        self, task_results: List[TaskResult], objective: str, max_concurrent: int = 3
    ) -> List[KnowledgeItem]:
        """
        Extract knowledge from multiple task results.

        Args:
            task_results: List of task results
            objective: Original objective for context
            max_concurrent: Maximum concurrent extractions

        Returns:
            Combined list of extracted knowledge items
        """
        import asyncio

        all_knowledge = []

        # Process in batches to avoid overwhelming the system
        for i in range(0, len(task_results), max_concurrent):
            batch = task_results[i : i + max_concurrent]

            # Create extraction tasks
            tasks = [self.extract_knowledge(result, objective) for result in batch]

            # Wait for batch to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect successful extractions
            for result in batch_results:
                if isinstance(result, list):
                    all_knowledge.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Batch extraction error: {result}")

        logger.info(
            f"Extracted {len(all_knowledge)} total knowledge items from "
            f"{len(task_results)} task results"
        )

        return all_knowledge
