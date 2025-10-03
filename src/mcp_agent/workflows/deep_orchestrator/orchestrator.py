"""
Deep Orchestrator - Production-ready adaptive workflow orchestration.

This module implements the main DeepOrchestrator class with comprehensive
planning, execution, knowledge management, and synthesis capabilities.
"""

import time
from collections import defaultdict
from typing import Callable, List, Optional, Type, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.logging.logger import get_logger
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
    ModelT,
    RequestParams,
)

from mcp_agent.workflows.deep_orchestrator.budget import SimpleBudget
from mcp_agent.workflows.deep_orchestrator.cache import AgentCache
from mcp_agent.workflows.deep_orchestrator.config import DeepOrchestratorConfig
from mcp_agent.workflows.deep_orchestrator.context_builder import ContextBuilder
from mcp_agent.workflows.deep_orchestrator.knowledge import KnowledgeExtractor
from mcp_agent.workflows.deep_orchestrator.memory import WorkspaceMemory
from mcp_agent.workflows.deep_orchestrator.models import (
    Plan,
    PolicyAction,
    VerificationResult,
)
from mcp_agent.workflows.deep_orchestrator.plan_verifier import PlanVerifier
from mcp_agent.workflows.deep_orchestrator.policy import PolicyEngine
from mcp_agent.workflows.deep_orchestrator.prompts import (
    EMERGENCY_RESPONDER_INSTRUCTION,
    ORCHESTRATOR_SYSTEM_INSTRUCTION,
    PLANNER_INSTRUCTION,
    SYNTHESIZER_INSTRUCTION,
    VERIFIER_INSTRUCTION,
    get_emergency_context,
    get_emergency_prompt,
    get_full_plan_prompt,
    get_planning_context,
    get_synthesis_context,
    get_synthesis_prompt,
    get_verification_context,
    get_verification_prompt,
)
from mcp_agent.workflows.deep_orchestrator.queue import TodoQueue
from mcp_agent.workflows.deep_orchestrator.task_executor import TaskExecutor
from mcp_agent.workflows.deep_orchestrator.utils import retry_with_backoff

if TYPE_CHECKING:
    from opentelemetry.trace.span import Span
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class DeepOrchestrator(AugmentedLLM[MessageParamT, MessageT]):
    """
    Production-ready adaptive orchestrator for deep research–style, long-horizon tasks.
    Coordinates specialized agents and MCP servers through comprehensive planning,
    iterative execution, knowledge accumulation, policy-driven replanning, and
    final synthesis.

    When to use this workflow:
    - Complex research tasks requiring extensive exploration and synthesis
    - Unknown task decomposition where subtasks emerge during execution
    - Long-running workflows that may require many iterations and replanning
    - Knowledge building across steps with persistent, reusable insights
    - Strict resource constraints (tokens, cost, time, context)
    - Adaptive requirements that benefit from policy-driven control

    Key capabilities:
    - Comprehensive upfront planning with dependency management
    - Dynamic agent design and caching optimized for each task
    - Parallel task execution with deduplication and dependency resolution
    - Knowledge extraction, categorization, and relevance-based retrieval
    - Smart context management (relevance scoring, compression, propagation)
    - Budget tracking for tokens, cost, time, and per-task context
    - Policy-driven decisions (continue, replan, force-complete, emergency stop)
    - Final synthesis that aggregates results, knowledge, and artifacts

    Examples:
    - Research: Multi-faceted literature/code research with consolidated findings
    - Code analysis: Security review with prioritized fix plan and applied changes
    - Content creation: Long-form content with examples, best practices, and pitfalls
    """

    def __init__(
        self,
        llm_factory: Callable[[Agent], AugmentedLLM[MessageParamT, MessageT]],
        config: Optional[DeepOrchestratorConfig] = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        """
        Initialize the adaptive orchestrator with production features.

        Args:
            llm_factory: Factory function to create LLMs
            config: Configuration object (if None, uses defaults)
            context: Application context
            **kwargs: Additional arguments for AugmentedLLM
        """
        # Use default config if none provided
        if config is None:
            config = DeepOrchestratorConfig()

        super().__init__(
            name=config.name,
            instruction=ORCHESTRATOR_SYSTEM_INSTRUCTION,
            context=context,
            **kwargs,
        )

        self.llm_factory = llm_factory
        self.config = config
        self.agents = {agent.name: agent for agent in config.available_agents}

        # Get available servers
        if config.available_servers:
            self.available_servers = config.available_servers
        elif context and hasattr(context, "server_registry"):
            self.available_servers = list(context.server_registry.registry.keys())
            logger.info(
                f"Detected {len(self.available_servers)} MCP servers from registry"
            )
        else:
            self.available_servers = []
            logger.warning("No MCP servers available")

        # Initialize core components
        self._initialize_components()

        # Tracking
        self.objective: str = ""
        self.iteration: int = 0
        self.replan_count: int = 0
        self.start_time: float = 0.0
        self.current_plan: Optional[Plan] = None

        logger.info(
            f"Initialized {config.name} with {len(self.agents)} agents, "
            f"{len(self.available_servers)} servers, max_iterations={config.execution.max_iterations}"
        )

    def _initialize_components(self):
        """Initialize all internal components."""
        # Core components
        self.memory = WorkspaceMemory(
            use_filesystem=self.config.execution.enable_filesystem
        )
        self.queue = TodoQueue()

        # Initialize budget with config values
        self.budget = SimpleBudget(
            max_tokens=self.config.budget.max_tokens,
            max_cost=self.config.budget.max_cost,
            max_time_minutes=self.config.budget.max_time_minutes,
            cost_per_1k_tokens=self.config.budget.cost_per_1k_tokens,
        )

        # Initialize policy with config values
        self.policy = PolicyEngine(
            max_consecutive_failures=self.config.policy.max_consecutive_failures,
            min_verification_confidence=self.config.policy.min_verification_confidence,
            replan_on_empty_queue=self.config.policy.replan_on_empty_queue,
            budget_critical_threshold=self.config.policy.budget_critical_threshold,
        )

        # Other components
        self.knowledge_extractor = KnowledgeExtractor(self.llm_factory, self.context)
        self.agent_cache = AgentCache(max_size=self.config.cache.max_cache_size)

        # Plan verifier
        self.plan_verifier = PlanVerifier(
            available_servers=self.available_servers,
            available_agents=self.agents,
        )

        # Context builder (will be updated with objective)
        self.context_builder = None

        # Task executor
        self.task_executor = None

    def _initialize_execution_components(self, objective: str):
        """Initialize components that depend on the objective."""
        self.objective = objective

        # Initialize context builder
        self.context_builder = ContextBuilder(
            objective=objective,
            memory=self.memory,
            queue=self.queue,
            task_context_budget=self.config.context.task_context_budget,
            context_relevance_threshold=self.config.context.context_relevance_threshold,
            context_compression_ratio=self.config.context.context_compression_ratio,
            enable_full_context_propagation=self.config.context.enable_full_context_propagation,
        )

        # Initialize task executor
        self.task_executor = TaskExecutor(
            llm_factory=self.llm_factory,
            agent_cache=self.agent_cache,
            knowledge_extractor=self.knowledge_extractor,
            context_builder=self.context_builder,
            memory=self.memory,
            available_agents=self.agents,
            objective=objective,
            context=self.context,
            max_task_retries=self.config.execution.max_task_retries,
            enable_parallel=self.config.execution.enable_parallel,
        )

        # Set budget update callback
        self.task_executor.set_budget_callback(self.budget.update_tokens)

    @track_tokens(node_type="workflow")
    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """
        Main execution entry point.

        Args:
            message: User objective or message
            request_params: Request parameters

        Returns:
            List of response messages
        """
        tracer = get_tracer(self.context)

        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.generate"
        ) as span:
            # Extract objective
            if isinstance(message, str):
                objective = message
            else:
                objective = await self._extract_objective(message)

            # Initialize execution components
            self._initialize_execution_components(objective)

            logger.info(f"Starting execution for objective: {objective[:100]}...")
            span.set_attribute("workflow.objective", objective[:200])

            # Execute workflow
            try:
                result = await self._execute_workflow(request_params, span)
                span.set_attribute("workflow.success", True)
                span.set_attribute("workflow.iterations", self.iteration)
                span.set_attribute("workflow.tokens_used", self.budget.tokens_used)
                span.set_attribute("workflow.cost", self.budget.cost_incurred)

                logger.info(
                    f"Execution completed successfully: "
                    f"{self.iteration} iterations, "
                    f"{self.budget.tokens_used} tokens, "
                    f"${self.budget.cost_incurred:.2f} cost"
                )

                # Log context usage statistics
                if self.context_builder:
                    context_stats = self.context_builder.get_context_usage_stats()
                    logger.info(
                        f"Context usage: {context_stats['tasks_with_full_context']} tasks with full context, "
                        f"{context_stats['tasks_with_compressed_context']} compressed, "
                        f"avg {context_stats['average_context_tokens']:.0f} tokens/task"
                    )

                return result

            except Exception as e:
                span.set_attribute("workflow.success", False)
                span.record_exception(e)
                logger.error(f"Workflow failed: {e}", exc_info=True)

                # Try to provide some value even on failure
                return await self._emergency_completion(str(e))

    async def _execute_workflow(
        self, request_params: Optional[RequestParams], span: "Span"
    ) -> List[MessageT]:
        """
        Core workflow execution logic with enhanced control.

        Args:
            request_params: Request parameters
            span: Tracing span

        Returns:
            Final response messages
        """
        self.start_time = time.time()
        self.iteration = 0
        self.replan_count = 0

        # Phase 1: Initial Planning
        span.add_event("phase_1_initial_planning")
        logger.info("Phase 1: Creating initial plan")

        initial_plan = await self._create_full_plan()

        if initial_plan.is_complete:
            logger.info("Objective already satisfied according to planner")
            return await self._create_simple_response(
                "The objective appears to be already satisfied."
            )

        self.queue.load_plan(initial_plan)

        # Main execution loop
        while self.iteration < self.config.execution.max_iterations:
            self.iteration += 1

            logger.info(f"\n{'=' * 60}")
            logger.info(f"Iteration {self.iteration} starting")
            logger.info(f"Queue status: {self.queue.get_progress_summary()}")
            logger.info(
                f"Budget usage: tokens={self.budget.tokens_used}, cost=${self.budget.cost_incurred:.2f}"
            )

            span.add_event(
                f"iteration_{self.iteration}_start",
                {
                    "queue_size": len(self.queue.pending_steps),
                    "completed": len(self.queue.completed_steps),
                    "tokens_used": self.budget.tokens_used,
                },
            )

            # Check if we need to take action based on policy
            verification_result = None
            if self.queue.is_empty():
                verification_result = await self._verify_completion()

            action = self.policy.decide_action(
                queue_empty=self.queue.is_empty(),
                verification_result=verification_result,
                budget=self.budget,
                iteration=self.iteration,
                max_iterations=self.config.execution.max_iterations,
            )

            logger.info(f"Policy decision: {action}")

            if action == PolicyAction.FORCE_COMPLETE:
                logger.warning("Forcing completion due to resource constraints")
                break

            elif action == PolicyAction.EMERGENCY_STOP:
                logger.error("Emergency stop triggered")
                raise RuntimeError("Emergency stop due to repeated failures")

            elif action == PolicyAction.REPLAN:
                if self.replan_count >= self.config.execution.max_replans:
                    logger.warning("Max replans reached, forcing completion")
                    break

                span.add_event(f"replanning_{self.replan_count + 1}")
                logger.info(
                    f"Replanning (attempt {self.replan_count + 1}/{self.config.execution.max_replans})"
                )

                new_plan = await self._create_full_plan()

                if new_plan.is_complete:
                    logger.info("Objective complete according to new plan")
                    break

                added = self.queue.merge_plan(new_plan)
                if added == 0:
                    logger.info("No new steps from replanning, completing")
                    break

                self.replan_count += 1
                continue

            # Execute next step
            next_step = self.queue.get_next_step()
            if not next_step:
                logger.info("No more steps to execute")
                break

            logger.info(
                f"Executing step: {next_step.description} ({len(next_step.tasks)} tasks)"
            )
            span.add_event(
                "executing_step",
                {"step": next_step.description, "tasks": len(next_step.tasks)},
            )

            # Execute all tasks in the step
            step_success = await self.task_executor.execute_step(
                next_step, request_params, self.executor
            )

            # Complete the step
            self.queue.complete_step(next_step)

            # Update policy based on results
            if step_success:
                self.policy.record_success()
            else:
                self.policy.record_failure()

            # Check context window and trim if needed
            context_size = self.memory.estimate_context_size()
            if context_size > 40000:  # Getting close to typical limits
                logger.warning(f"Context size high: ~{context_size} tokens")
                self.memory.trim_for_context(30000)

        # Phase 3: Final Synthesis
        span.add_event("phase_3_final_synthesis")
        logger.info("\nPhase 3: Creating final synthesis")
        return await self._create_final_synthesis()

    async def _create_full_plan(self) -> Plan:
        """
        Create a comprehensive execution plan with XML-structured prompts.

        Returns:
            Complete execution plan
        """
        # Build planning context
        completed_steps = [step.description for step in self.queue.completed_steps[-5:]]
        relevant_knowledge = self.memory.get_relevant_knowledge(
            self.objective, limit=10
        )

        # Convert knowledge items to dict format for prompt
        knowledge_items = [
            {
                "key": item.key,
                "value": item.value,
                "confidence": item.confidence,
                "category": item.category,
            }
            for item in relevant_knowledge
        ]

        # Create planning agent
        planner = Agent(
            name="StrategicPlanner",
            instruction=PLANNER_INSTRUCTION,
            context=self.context,
        )

        llm = self.llm_factory(planner)

        # Try to create a valid plan with retries
        max_verification_attempts = 10
        previous_plan: Plan = None
        previous_errors = None

        for attempt in range(max_verification_attempts):
            # Build context (may include previous errors)
            context = get_planning_context(
                objective=self.objective,
                progress_summary=self.queue.get_progress_summary()
                if self.queue.completed_steps
                else "",
                completed_steps=completed_steps,
                knowledge_items=knowledge_items,
                available_servers=self.available_servers,
                available_agents=self.agents,
            )

            # Add previous plan and errors if this is a retry
            if previous_plan and previous_errors:
                context += "\n\n<previous_failed_plan>\n"
                context += previous_plan.model_dump_json(indent=2)
                context += "\n</previous_failed_plan>"

                context += f"\n\n<plan_errors>\n{previous_errors.get_error_summary()}\n</plan_errors>"
                context += "\n<important>The previous plan shown above had errors. Create a new plan that fixes ALL the issues listed. Pay special attention to:"
                context += "\n  - Only use MCP servers from the available_servers list"
                context += "\n  - Ensure all task names are unique"
                context += (
                    "\n  - Dependencies can only reference tasks from previous steps"
                )
                context += "\n</important>"

            # Push token counter context for this planning attempt
            if self.context and hasattr(self.context, "token_counter"):
                await self.context.token_counter.push(
                    name=f"planning_attempt_{attempt}",
                    node_type="planning",
                    metadata={"attempt": attempt},
                )

            # Get structured plan
            prompt = get_full_plan_prompt(context)
            plan: Plan = await retry_with_backoff(
                lambda: llm.generate_structured(message=prompt, response_model=Plan),
                max_attempts=2,
            )

            # Pop planning context and update budget
            if self.context and hasattr(self.context, "token_counter"):
                planning_node = await self.context.token_counter.pop()
                if planning_node:
                    planning_usage = planning_node.aggregate_usage()
                    self.budget.update_tokens(planning_usage.total_tokens)

            # Verify the plan
            verification_result = self.plan_verifier.verify_plan(plan)

            if verification_result.is_valid:
                logger.info(
                    f"Created valid plan: {len(plan.steps)} steps, reasoning: {plan.reasoning[:100]}..."
                )
                if verification_result.warnings:
                    logger.warning(
                        f"Plan warnings: {', '.join(verification_result.warnings)}"
                    )

                self.current_plan = plan
                return plan

            else:
                logger.warning(
                    f"Plan verification failed (attempt {attempt + 1}/{max_verification_attempts}): "
                    f"{len(verification_result.errors)} errors found"
                )

                # Store for next iteration
                previous_plan = plan
                previous_errors = verification_result

                if attempt == max_verification_attempts - 1:
                    # Final attempt failed
                    logger.error(
                        f"Failed to create valid plan after {max_verification_attempts} attempts"
                    )
                    logger.error(verification_result.get_error_summary())

                    # Return the plan anyway with a warning
                    self.current_plan = plan
                    return plan

        # Should not reach here
        raise RuntimeError("Failed to create a valid plan")

    async def _verify_completion(self) -> tuple[bool, float]:
        """
        Verify if the objective has been completed.

        Returns:
            Tuple of (is_complete, confidence)
        """
        logger.info("Verifying objective completion...")

        verifier = Agent(
            name="ObjectiveVerifier",
            instruction=VERIFIER_INSTRUCTION,
            context=self.context,
        )

        llm = self.llm_factory(verifier)

        # Build verification context
        context = get_verification_context(
            objective=self.objective,
            progress_summary=self.queue.get_progress_summary(),
            knowledge_summary=self.memory.get_knowledge_summary(limit=15),
            artifacts=self.memory.artifacts,
        )

        prompt = get_verification_prompt(context)

        result = await llm.generate_structured(
            message=prompt, response_model=VerificationResult
        )

        logger.info(
            f"Verification result: complete={result.is_complete}, "
            f"confidence={result.confidence}, "
            f"missing={len(result.missing_elements)}, "
            f"reasoning: {result.reasoning[:100]}..."
        )

        return result.is_complete, result.confidence

    async def _create_final_synthesis(self) -> List[MessageT]:
        """
        Create the final deliverable from all work.

        Returns:
            Final synthesis messages
        """
        logger.info("Creating final synthesis of all work...")

        synthesizer = Agent(
            name="FinalSynthesizer",
            instruction=SYNTHESIZER_INSTRUCTION,
            server_names=self.available_servers,
            context=self.context,
        )

        # Build synthesis context
        execution_summary = {
            "iterations": self.iteration,
            "steps_completed": len(self.queue.completed_steps),
            "tasks_completed": len(self.queue.completed_task_names),
            "tokens_used": self.budget.tokens_used,
            "cost": self.budget.cost_incurred,
        }

        # Prepare completed steps with results
        completed_steps = []
        for step in self.queue.completed_steps:
            step_data = {"description": step.description, "task_results": []}

            # Get results for tasks in this step
            step_task_names = {t.name for t in step.tasks}
            step_results = [
                r for r in self.memory.task_results if r.task_name in step_task_names
            ]

            for result in step_results:
                if result.success and result.output:
                    task = self.queue.all_tasks.get(result.task_name)
                    task_desc = task.description if task else "Unknown task"

                    step_data["task_results"].append(
                        {
                            "description": task_desc,
                            "output": result.output,
                            "success": True,
                        }
                    )

            completed_steps.append(step_data)

        # Group knowledge by category
        knowledge_by_category = defaultdict(list)
        for item in self.memory.knowledge:
            knowledge_by_category[item.category].append(item)

        context = get_synthesis_context(
            objective=self.objective,
            execution_summary=execution_summary,
            completed_steps=completed_steps,
            knowledge_by_category=dict(knowledge_by_category),
            artifacts=self.memory.artifacts,
        )

        prompt = get_synthesis_prompt(context)

        # Generate synthesis
        async with synthesizer:
            llm = await synthesizer.attach_llm(self.llm_factory)

            result = await llm.generate(
                message=prompt, request_params=RequestParams(max_iterations=5)
            )

            logger.info("Final synthesis completed")
            return result

    async def _emergency_completion(self, error: str) -> List[MessageT]:
        """
        Provide best-effort response when workflow fails.

        Args:
            error: Error message

        Returns:
            Emergency response messages
        """
        logger.warning(f"Entering emergency completion mode due to: {error}")

        emergency_agent = Agent(
            name="EmergencyResponder",
            instruction=EMERGENCY_RESPONDER_INSTRUCTION,
            context=self.context,
        )

        # Prepare partial knowledge
        partial_knowledge = [
            {"key": item.key, "value": item.value}
            for item in self.memory.knowledge[:10]
        ]

        # Get artifact names
        artifacts_created = (
            list(self.memory.artifacts.keys())[:5] if self.memory.artifacts else None
        )

        context = get_emergency_context(
            objective=self.objective,
            error=error,
            progress_summary=self.queue.get_progress_summary(),
            partial_knowledge=partial_knowledge,
            artifacts_created=artifacts_created,
        )

        prompt = get_emergency_prompt(context)

        async with emergency_agent:
            llm = await emergency_agent.attach_llm(self.llm_factory)
            return await llm.generate(message=prompt)

    async def _extract_objective(
        self, message: MessageParamT | List[MessageParamT]
    ) -> str:
        """
        Extract objective from complex message types.

        Args:
            message: Input message

        Returns:
            Extracted objective string
        """
        extractor = Agent(
            name="ObjectiveExtractor",
            instruction="""
            The message that will be provided to you will be a user message. 
            Your job is to extract the user's objective or request from their message. 
            Be concise and clear. You must be able to answer: 'What is the user asking for in this message?'
            """,
            context=self.context,
        )

        llm = self.llm_factory(extractor)

        return await llm.generate_str(
            message=message,
            request_params=RequestParams(max_iterations=1),
        )

    async def _create_simple_response(self, content: str) -> List[MessageT]:
        """
        Create a simple response message.

        Args:
            content: Response content

        Returns:
            Response messages
        """
        simple_agent = Agent(
            name="SimpleResponder",
            instruction="Provide a clear, direct response.",
            context=self.context,
        )

        async with simple_agent:
            llm = await simple_agent.attach_llm(self.llm_factory)
            return await llm.generate(message=content)

    async def generate_str(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> str:
        """Generate and return string representation."""
        messages = await self.generate(message, request_params)
        if messages:
            # This is simplified - real implementation would use proper message conversion
            return str(messages[0])
        return ""

    async def generate_structured(
        self,
        message: str | MessageParamT | List[MessageParamT],
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Generate structured output."""
        result_str = await self.generate_str(message, request_params)

        parser = Agent(
            name="StructuredParser",
            instruction="Parse the content into the requested structure accurately.",
            context=self.context,
        )

        llm = self.llm_factory(parser)

        return await llm.generate_structured(
            message=f"<parse_request>\n{result_str}\n</parse_request>",
            response_model=response_model,
            request_params=RequestParams(max_iterations=1),
        )
