"""
Task queue management for the Deep Orchestrator workflow.

This module handles task queueing with deduplication and progress tracking.
Steps run sequentially, tasks within a step run in parallel.
"""

from typing import Dict, List, Optional, Set, Tuple

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.models import Plan, Step, Task

logger = get_logger(__name__)


class TodoQueue:
    """
    Task queue with deduplication and progress tracking.

    This class manages the execution queue for tasks and steps,
    handling deduplication and progress tracking. Steps run sequentially,
    tasks within a step run in parallel.
    """

    def __init__(self):
        """Initialize the todo queue."""
        # Queue state
        self.pending_steps: List[Step] = []
        self.completed_steps: List[Step] = []

        # Task tracking
        self.all_tasks: Dict[str, Task] = {}  # task_name -> Task
        self.completed_task_names: Set[str] = set()
        self.failed_task_names: Dict[str, int] = {}  # task_name -> retry count

        # Deduplication tracking
        self.seen_step_descriptions: Set[str] = set()
        self.seen_task_hashes: Set[Tuple[str, ...]] = set()

        logger.debug("Initialized TodoQueue")

    def load_plan(self, plan: Plan) -> None:
        """
        Load a new plan into the queue.

        Args:
            plan: Plan to load
        """
        added_steps = 0
        added_tasks = 0

        for step in plan.steps:
            filtered_step = self._filter_step(step)
            if filtered_step and filtered_step.tasks:
                self.pending_steps.append(filtered_step)
                self.seen_step_descriptions.add(step.description)
                added_steps += 1
                added_tasks += len(filtered_step.tasks)

        logger.debug(f"Loaded plan: {added_steps} steps, {added_tasks} tasks")

    def merge_plan(self, plan: Plan) -> int:
        """
        Merge a new plan, deduplicating existing work.

        Args:
            plan: Plan to merge

        Returns:
            Number of new steps added
        """
        initial_count = len(self.pending_steps)

        for step in plan.steps:
            filtered_step = self._filter_step(step)
            if filtered_step and filtered_step.tasks:
                self.pending_steps.append(filtered_step)
                self.seen_step_descriptions.add(step.description)

        added = len(self.pending_steps) - initial_count
        logger.debug(f"Merged plan: {added} new steps added")
        return added

    def _filter_step(self, step: Step) -> Optional[Step]:
        """
        Filter out duplicate steps and tasks.

        Args:
            step: Step to filter

        Returns:
            Filtered step or None if entirely duplicate
        """
        # Skip if step already seen
        if step.description in self.seen_step_descriptions:
            logger.debug(f"Skipping duplicate step: {step.description}")
            return None

        # Filter tasks
        filtered_tasks = []
        for task in step.tasks:
            task_hash = task.get_hash_key()

            # Skip if task already seen
            if task_hash in self.seen_task_hashes:
                logger.debug(f"Skipping duplicate task: {task.description}")
                continue

            self.seen_task_hashes.add(task_hash)
            self.all_tasks[task.name] = task
            filtered_tasks.append(task)

        if filtered_tasks:
            step.tasks = filtered_tasks
            return step

        return None

    def get_next_step(self) -> Optional[Step]:
        """
        Get the next step to execute.

        Returns:
            Next step or None if queue is empty
        """
        if self.pending_steps:
            return self.pending_steps[0]
        return None

    def complete_step(self, step: Step) -> None:
        """
        Mark a step as completed.

        Args:
            step: Step to mark as completed
        """
        # Remove from pending if present
        if step in self.pending_steps:
            self.pending_steps.remove(step)

        step.completed = True
        self.completed_steps.append(step)

        # Mark successful tasks as completed
        completed_count = 0
        for task in step.tasks:
            if task.status == "completed":
                self.completed_task_names.add(task.name)
                completed_count += 1
                logger.debug(f"Task completed: {task.name} - {task.description}")

        logger.debug(
            f"Step completed: {step.description} "
            f"({completed_count}/{len(step.tasks)} tasks successful)"
        )

    def mark_task_failed(self, task_name: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_name: Name of the failed task
        """
        current_count = self.failed_task_names.get(task_name, 0)
        self.failed_task_names[task_name] = current_count + 1
        logger.debug(
            f"Task marked as failed: {task_name} (attempt {current_count + 1})"
        )

    def is_empty(self) -> bool:
        """
        Check if queue is empty.

        Returns:
            True if no pending steps
        """
        return len(self.pending_steps) == 0

    def has_ready_tasks(self) -> bool:
        """
        Check if there are any tasks ready to execute.

        Returns:
            True if there are pending steps
        """
        return len(self.pending_steps) > 0

    def get_task_by_name(self, task_name: str) -> Optional[Task]:
        """
        Get a task by its name.

        Args:
            task_name: Name of the task

        Returns:
            Task if found, None otherwise
        """
        return self.all_tasks.get(task_name)

    def get_progress_summary(self) -> str:
        """
        Get a detailed progress summary.

        Returns:
            Human-readable progress summary
        """
        total_steps = len(self.completed_steps) + len(self.pending_steps)
        total_tasks = len(self.all_tasks)
        completed_tasks = len(self.completed_task_names)
        failed_tasks = len(self.failed_task_names)

        if total_steps == 0:
            return "No steps planned yet."

        lines = [
            f"Progress: {len(self.completed_steps)}/{total_steps} steps",
            f"Tasks: {completed_tasks}/{total_tasks} completed, {failed_tasks} failed",
        ]

        # Add pending info
        if self.pending_steps:
            pending_task_count = sum(len(s.tasks) for s in self.pending_steps)
            lines.append(
                f"Pending: {len(self.pending_steps)} steps, {pending_task_count} tasks"
            )

        return " | ".join(lines)

    def clear(self) -> None:
        """Clear the queue."""
        self.pending_steps.clear()
        self.completed_steps.clear()
        self.all_tasks.clear()
        self.completed_task_names.clear()
        self.failed_task_names.clear()
        self.seen_step_descriptions.clear()
        self.seen_task_hashes.clear()
        logger.debug("Queue cleared")

    def enqueue_step(self, step: Step) -> None:
        """
        Enqueue a single step to the queue.

        Args:
            step: Step to enqueue
        """
        filtered_step = self._filter_step(step)
        if filtered_step and filtered_step.tasks:
            self.pending_steps.append(filtered_step)
            self.seen_step_descriptions.add(step.description)
            logger.debug(
                f"Enqueued step: {step.description} with {len(filtered_step.tasks)} tasks"
            )

    def dequeue_step(self) -> Optional[Step]:
        """
        Dequeue and return the next step from the queue.

        Returns:
            Next step or None if queue is empty
        """
        if self.pending_steps:
            step = self.pending_steps.pop(0)
            logger.debug(f"Dequeued step: {step.description}")
            return step
        return None
