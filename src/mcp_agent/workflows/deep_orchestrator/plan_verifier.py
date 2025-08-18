"""
Plan verification utilities for the Deep Orchestrator workflow.

This module handles validation of execution plans to ensure correctness
before execution begins.
"""

from typing import Dict, List

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.models import Plan, PlanVerificationResult

logger = get_logger(__name__)


class PlanVerifier:
    """Verifies execution plans for correctness and validity."""

    def __init__(
        self,
        available_servers: List[str],
        available_agents: Dict[str, any],
    ):
        """
        Initialize the plan verifier.

        Args:
            available_servers: List of available MCP servers
            available_agents: Dictionary of available agents
        """
        self.available_servers = available_servers
        self.available_agents = available_agents

    def verify_plan(self, plan: Plan) -> PlanVerificationResult:
        """
        Verify the plan for correctness, collecting all errors.

        Returns a PlanVerificationResult with all errors found.
        This method is modular - add more verification steps as needed.

        Args:
            plan: Plan to verify

        Returns:
            Verification result with any errors found
        """
        result = PlanVerificationResult(is_valid=True)

        # Verification step 1: Check MCP server validity
        self._verify_mcp_servers(plan, result)

        # Verification step 2: Check agent name validity
        self._verify_agent_names(plan, result)

        # Verification step 3: Check task name uniqueness
        self._verify_task_names(plan, result)

        # Verification step 4: Check dependency references
        self._verify_dependencies(plan, result)

        # Verification step 5: Check for basic task validity
        self._verify_task_validity(plan, result)

        # Log successful verification
        if result.is_valid:
            logger.info("Plan verification succeeded")

        return result

    def _verify_mcp_servers(self, plan: Plan, result: PlanVerificationResult) -> None:
        """Verify all MCP servers in the plan are valid."""
        available_set = set(self.available_servers)

        for step_idx, step in enumerate(plan.steps):
            for task in step.tasks:
                if task.servers:
                    for server in task.servers:
                        if server not in available_set:
                            result.add_error(
                                category="invalid_server",
                                message=f"Server '{server}' is not available (available: {', '.join(self.available_servers) if self.available_servers else 'None'})",
                                step_index=step_idx,
                                task_name=task.name,
                                details={
                                    "invalid_server": server,
                                    "available_servers": list(self.available_servers),
                                    "step_description": step.description,
                                },
                            )

    def _verify_agent_names(self, plan: Plan, result: PlanVerificationResult) -> None:
        """Verify all specified agent names are valid."""
        available_agent_names = set(self.available_agents.keys())

        for step_idx, step in enumerate(plan.steps):
            for task in step.tasks:
                # Only verify if agent is specified (not None)
                if task.agent is not None:
                    if task.agent not in available_agent_names:
                        result.add_error(
                            category="invalid_agent",
                            message=f"Agent '{task.agent}' is not available (available: {', '.join(available_agent_names) if available_agent_names else 'None'})",
                            step_index=step_idx,
                            task_name=task.name,
                            details={
                                "invalid_agent": task.agent,
                                "available_agents": list(available_agent_names),
                                "step_description": step.description,
                                "task_description": task.description,
                            },
                        )

    def _verify_task_names(self, plan: Plan, result: PlanVerificationResult) -> None:
        """Verify all task names are unique."""
        seen_names = {}

        for step_idx, step in enumerate(plan.steps):
            for task in step.tasks:
                if task.name in seen_names:
                    first_step_idx, first_step_desc = seen_names[task.name]
                    result.add_error(
                        category="duplicate_name",
                        message=f"Task name '{task.name}' is duplicated (first seen in step {first_step_idx + 1}: {first_step_desc})",
                        step_index=step_idx,
                        task_name=task.name,
                        details={
                            "first_occurrence_step": first_step_idx + 1,
                            "duplicate_step": step_idx + 1,
                        },
                    )
                else:
                    seen_names[task.name] = (step_idx, step.description)

    def _verify_dependencies(self, plan: Plan, result: PlanVerificationResult) -> None:
        """Verify all task dependencies reference valid previous tasks."""
        # Build a map of task names to their step index
        task_step_map = {}
        for step_idx, step in enumerate(plan.steps):
            for task in step.tasks:
                task_step_map[task.name] = step_idx

        # Check each task's dependencies
        for step_idx, step in enumerate(plan.steps):
            for task in step.tasks:
                if task.requires_context_from:
                    for dep_name in task.requires_context_from:
                        if dep_name not in task_step_map:
                            result.add_error(
                                category="invalid_dependency",
                                message=f"References non-existent task '{dep_name}'",
                                step_index=step_idx,
                                task_name=task.name,
                                details={
                                    "missing_dependency": dep_name,
                                    "available_tasks": list(task_step_map.keys()),
                                },
                            )
                        elif task_step_map[dep_name] >= step_idx:
                            dep_step = task_step_map[dep_name]
                            result.add_error(
                                category="invalid_dependency",
                                message=f"References task '{dep_name}' from step {dep_step + 1} (can only reference previous steps)",
                                step_index=step_idx,
                                task_name=task.name,
                                details={
                                    "dependency_name": dep_name,
                                    "dependency_step": dep_step + 1,
                                    "current_step": step_idx + 1,
                                },
                            )

    def _verify_task_validity(self, plan: Plan, result: PlanVerificationResult) -> None:
        """Verify basic task validity."""
        for step_idx, step in enumerate(plan.steps):
            # Check step has tasks
            if not step.tasks:
                result.add_error(
                    category="empty_step",
                    message=f"Step '{step.description}' has no tasks",
                    step_index=step_idx,
                    details={"step_description": step.description},
                )

            for task in step.tasks:
                # Check task has a name
                if not task.name or not task.name.strip():
                    result.add_error(
                        category="invalid_task",
                        message="Task has no name",
                        step_index=step_idx,
                        details={"task_description": task.description},
                    )

                # Check task has a description
                if not task.description or not task.description.strip():
                    result.add_error(
                        category="invalid_task",
                        message=f"Task '{task.name}' has no description",
                        step_index=step_idx,
                        task_name=task.name,
                    )

                # Warn about extremely high context budgets
                if task.context_window_budget > 80000:
                    result.warnings.append(
                        f"Task '{task.name}' has very high context budget ({task.context_window_budget} tokens)"
                    )
