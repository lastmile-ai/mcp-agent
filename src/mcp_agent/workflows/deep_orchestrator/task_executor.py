"""
Task execution utilities for the Deep Orchestrator workflow.

This module handles the execution of individual tasks including
agent creation, context building, and result processing.
"""

import asyncio
import time
from typing import Callable, Optional, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.deep_orchestrator.cache import AgentCache
from mcp_agent.workflows.deep_orchestrator.context_builder import ContextBuilder
from mcp_agent.workflows.deep_orchestrator.knowledge import KnowledgeExtractor
from mcp_agent.workflows.deep_orchestrator.memory import WorkspaceMemory
from mcp_agent.workflows.deep_orchestrator.models import (
    AgentDesign,
    Step,
    Task,
    TaskResult,
    TaskStatus,
)
from mcp_agent.workflows.deep_orchestrator.prompts import (
    AGENT_DESIGNER_INSTRUCTION,
    build_agent_instruction,
    get_agent_design_prompt,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class TaskExecutor:
    """Handles execution of individual tasks with retry logic and agent management."""

    def __init__(
        self,
        llm_factory: Callable[[Agent], AugmentedLLM],
        agent_cache: AgentCache,
        knowledge_extractor: KnowledgeExtractor,
        context_builder: ContextBuilder,
        memory: WorkspaceMemory,
        available_agents: dict,
        objective: str,
        context: Optional["Context"] = None,
        max_task_retries: int = 3,
        enable_parallel: bool = True,
    ):
        """
        Initialize the task executor.

        Args:
            llm_factory: Factory function to create LLMs
            agent_cache: Cache for dynamically created agents
            knowledge_extractor: Extractor for knowledge from task outputs
            context_builder: Builder for task execution contexts
            memory: Workspace memory for results
            available_agents: Dictionary of available predefined agents
            objective: The main objective being worked on
            context: Application context
            max_task_retries: Maximum retries per failed task
            enable_parallel: Whether to enable parallel execution
        """
        self.llm_factory = llm_factory
        self.agent_cache = agent_cache
        self.knowledge_extractor = knowledge_extractor
        self.context_builder = context_builder
        self.memory = memory
        self.available_agents = available_agents
        self.objective = objective
        self.context = context
        self.max_task_retries = max_task_retries
        self.enable_parallel = enable_parallel

        # Budget update callback (will be set by orchestrator)
        self.update_budget_tokens = lambda tokens: None

    def set_budget_callback(self, update_budget_tokens: Callable[[int], None]):
        """
        Set budget update callback.

        Args:
            update_budget_tokens: Function to update budget with token usage
        """
        self.update_budget_tokens = update_budget_tokens

    async def execute_step(
        self,
        step: Step,
        request_params: Optional[RequestParams],
        executor=None,
    ) -> bool:
        """
        Execute all tasks in a step with parallel support.

        Args:
            step: Step to execute
            request_params: Request parameters
            executor: Optional executor for parallel execution

        Returns:
            True if all tasks succeeded
        """
        logger.info(f"Executing step with {len(step.tasks)} tasks")

        # Push token counter context for this step
        if self.context and hasattr(self.context, "token_counter"):
            await self.context.token_counter.push(
                name=f"step_{step.description[:50]}",
                node_type="step",
                metadata={
                    "description": step.description,
                    "num_tasks": len(step.tasks),
                },
            )

        # Prepare tasks for execution
        if self.enable_parallel and executor and len(step.tasks) > 1:
            # Parallel execution with streaming results
            logger.info("Executing tasks in parallel")
            task_coroutines = [
                self.execute_task(task, request_params) for task in step.tasks
            ]
            results = await executor.execute_many(task_coroutines)
        else:
            # Sequential execution
            logger.info("Executing tasks sequentially")
            results = []
            for task in step.tasks:
                result = await self.execute_task(task, request_params)
                results.append(result)

        # Pop the step context and get its token usage for budget tracking
        if self.context and hasattr(self.context, "token_counter"):
            step_node = await self.context.token_counter.pop()
            if step_node:
                # Get the aggregated usage for this entire step (all tasks)
                step_usage = step_node.aggregate_usage()
                step_tokens = step_usage.total_tokens

                # Update budget with tokens used by this step
                self.update_budget_tokens(step_tokens)

        # Check overall success
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        logger.info(
            f"Step execution complete: {successful} successful, {failed} failed"
        )

        return failed == 0

    async def execute_task(
        self, task: Task, request_params: Optional[RequestParams]
    ) -> TaskResult:
        """
        Execute a single task with retry logic.

        Args:
            task: Task to execute
            request_params: Request parameters

        Returns:
            Task execution result
        """
        logger.info(f"Executing task: {task.description[:100]}...")

        # Try with retries
        for attempt in range(self.max_task_retries):
            try:
                result = await self._execute_task_once(task, request_params, attempt)

                if result.success:
                    return result

                # Task failed, maybe retry
                if attempt < self.max_task_retries - 1:
                    logger.warning(
                        f"Task failed, retrying (attempt {attempt + 2}/{self.max_task_retries})"
                    )
                    await asyncio.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                logger.error(f"Task execution error: {e}")
                if attempt == self.max_task_retries - 1:
                    # Final attempt, return failure
                    return TaskResult(
                        task_name=task.name,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        retry_count=attempt + 1,
                    )

        # All retries exhausted
        return result

    async def _execute_task_once(
        self, task: Task, request_params: Optional[RequestParams], attempt: int
    ) -> TaskResult:
        """
        Execute a single task attempt.

        Args:
            task: Task to execute
            request_params: Request parameters
            attempt: Current attempt number

        Returns:
            Task execution result
        """
        start_time = time.time()
        result = TaskResult(
            task_name=task.name, status=TaskStatus.IN_PROGRESS, retry_count=attempt
        )

        try:
            # Get or create agent
            agent = await self._get_or_create_agent(task)

            # Build task context
            task_context = self.context_builder.build_task_context(task)

            # Execute with agent
            if isinstance(agent, AugmentedLLM):
                output = await agent.generate_str(
                    message=task_context,
                    request_params=request_params or RequestParams(max_iterations=10),
                )
            else:
                async with agent:
                    llm = await agent.attach_llm(self.llm_factory)
                    output = await llm.generate_str(
                        message=task_context,
                        request_params=request_params
                        or RequestParams(max_iterations=10),
                    )

            # Success
            result.status = TaskStatus.COMPLETED
            result.output = output
            result.duration_seconds = time.time() - start_time

            # Extract artifacts if mentioned
            if any(
                phrase in output.lower()
                for phrase in ["created file:", "saved to:", "wrote to:"]
            ):
                result.artifacts[f"task_{task.name}_output"] = output

            # Extract knowledge
            knowledge_items = await self.knowledge_extractor.extract_knowledge(
                result, self.objective
            )
            result.knowledge_extracted = knowledge_items

            # Update task status
            task.status = TaskStatus.COMPLETED

            logger.info(
                f"Task completed: {task.name} "
                f"(duration: {result.duration_seconds:.1f}s)"
            )

        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
            result.duration_seconds = time.time() - start_time
            task.status = TaskStatus.FAILED
            logger.error(f"Task {task.name} failed: {e}")

        # Record result
        self.memory.add_task_result(result)
        return result

    async def _get_or_create_agent(self, task: Task) -> Agent:
        """
        Get or create an agent for a task.

        Args:
            task: Task to get/create agent for

        Returns:
            Agent instance
        """
        if task.agent is None:
            # Check cache first
            cache_key = self.agent_cache.get_key(task.description, task.servers)
            agent = self.agent_cache.get(cache_key)

            if not agent:
                agent = await self._create_dynamic_agent(task)
                self.agent_cache.put(cache_key, agent)

            return agent

        elif task.agent and task.agent in self.available_agents:
            agent = self.available_agents[task.agent]
            logger.debug(f"Using predefined agent: {task.agent}")
            return agent

        else:
            # Default agent
            logger.warning(
                f'Task "{task.name}" ({task.description}) requested agent "{task.agent}" which is not available. '
                f"Creating default agent. Available agents: {list(self.available_agents.keys())}"
            )
            return Agent(
                name=f"TaskExecutor_{task.name}",
                instruction="You are a capable task executor. Complete the given task thoroughly using available tools.",
                server_names=task.servers,
                context=self.context,
            )

    async def _create_dynamic_agent(self, task: Task) -> Agent:
        """
        Dynamically create an optimized agent for a task.

        Args:
            task: Task to create agent for

        Returns:
            Dynamically created agent
        """
        logger.debug(f"Creating dynamic agent for task: {task.description[:50]}...")

        # Agent designer
        designer = Agent(
            name="AgentDesigner",
            instruction=AGENT_DESIGNER_INSTRUCTION,
            context=self.context,
        )

        llm = self.llm_factory(designer)

        # Design agent
        design_prompt = get_agent_design_prompt(
            task.description, task.servers, self.objective
        )

        design = await llm.generate_structured(
            message=design_prompt, response_model=AgentDesign
        )

        # Build comprehensive instruction
        instruction = build_agent_instruction(design.model_dump())

        agent = Agent(
            name=design.name,
            instruction=instruction,
            server_names=task.servers,
            context=self.context,
        )

        logger.debug(f"Created agent '{design.name}' with role: {design.role}")
        return agent
