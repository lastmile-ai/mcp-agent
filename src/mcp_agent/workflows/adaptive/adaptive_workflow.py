"""
Adaptive Workflow - Following Deep Research Architecture
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Type, Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
    MessageTypes,
    ModelT,
    RequestParams,
)
from mcp.types import ModelPreferences
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.logging.logger import get_logger

from mcp_agent.workflows.adaptive.models import (
    TaskType,
    ResearchAspect,
    SubagentResult,
    SynthesisDecision,
    ExecutionResult,
)
from mcp_agent.workflows.adaptive.memory import MemoryManager
from mcp_agent.workflows.adaptive.prompts import (
    LEAD_RESEARCHER_ANALYZE_PROMPT,
    LEAD_RESEARCHER_PLAN_PROMPT,
    LEAD_RESEARCHER_SYNTHESIZE_PROMPT,
    LEAD_RESEARCHER_DECIDE_PROMPT,
    RESEARCH_SUBAGENT_TEMPLATE,
    ACTION_SUBAGENT_TEMPLATE,
    FINAL_REPORT_PROMPT,
    BEAST_MODE_PROMPT,
)
from mcp_agent.workflows.adaptive.subtask_queue import (
    AdaptiveSubtaskQueue,
    SubtaskQueueItem,
)
from mcp_agent.workflows.adaptive.knowledge_manager import (
    EnhancedExecutionMemory,
    KnowledgeExtractor,
)
from mcp_agent.workflows.adaptive.budget_manager import (
    BudgetManager,
    ActionType as BudgetActionType,
)
from mcp_agent.workflows.adaptive.action_controller import (
    ActionController,
    WorkflowAction,
)
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)
from mcp_agent.workflows.adaptive.error_handler import WorkflowErrorHandler
from mcp_agent.tracing.token_tracking_decorator import track_tokens

logger = get_logger(__name__)


class AdaptiveWorkflow(AugmentedLLM[MessageParamT, MessageT]):
    """
    Adaptive workflow following the Deep Research architecture.

    Key principles:
    - Lead Researcher maintains control throughout
    - Subagents created dynamically for specific aspects
    - Iterative refinement until objective is met
    - Clear synthesis and decision phases
    """

    def __init__(
        self,
        llm_factory: Callable[[Agent], AugmentedLLM[MessageParamT, MessageT]],
        name: str | None = None,
        available_agents: List[Agent | AugmentedLLM] | None = None,
        available_servers: List[str] | None = None,
        time_budget: timedelta = timedelta(minutes=30),
        cost_budget: float = 10.0,
        max_iterations: int = 10,
        enable_parallel: bool = True,
        enable_validation: bool = True,  # Enable result validation
        memory_manager: Optional[MemoryManager] = None,
        model_preferences: Optional[ModelPreferences] = None,
        context: Optional[Any] = None,
        # New configurable parameters
        synthesis_frequency: int = 3,  # Synthesize every N iterations
        min_knowledge_for_synthesis: int = 5,  # Min knowledge items before synthesis
        max_subtask_depth: int = 3,  # Max depth for task decomposition
        beast_mode_temperature: float = 0.9,  # Temperature for beast mode
        token_budget: int = 100000,  # Token budget
        **kwargs,
    ):
        """Initialize Adaptive Workflow V2"""
        super().__init__(
            name=name or "AdaptiveWorkflowV2",
            instruction="I am a lead researcher coordinating investigation into your objective.",
            context=context,
            **kwargs,
        )

        self.llm_factory = llm_factory
        self.available_agents = {}
        # Process available agents - handle both Agent and AugmentedLLM instances
        for agent in available_agents or []:
            if isinstance(agent, Agent):
                self.available_agents[agent.name] = agent
            elif hasattr(agent, "name"):
                # It's an AugmentedLLM instance
                self.available_agents[agent.name] = agent

        self.available_servers = available_servers or []
        self.time_budget = time_budget
        self.cost_budget = cost_budget
        self.max_iterations = max_iterations
        self.enable_parallel = enable_parallel
        self.enable_validation = enable_validation
        self.memory_manager = memory_manager or MemoryManager()

        # Store new configurable parameters
        self.synthesis_frequency = synthesis_frequency
        self.min_knowledge_for_synthesis = min_knowledge_for_synthesis
        self.max_subtask_depth = max_subtask_depth
        self.beast_mode_temperature = beast_mode_temperature
        self.token_budget = token_budget
        self.model_preferences = model_preferences

        # Track current workflow
        self._current_execution_id: Optional[str] = None
        self._current_memory: Optional[EnhancedExecutionMemory] = None

        # New components
        self.subtask_queue: Optional[AdaptiveSubtaskQueue] = None
        self.budget_manager: Optional[BudgetManager] = None
        self.action_controller: Optional[ActionController] = None
        self.knowledge_extractor: Optional[KnowledgeExtractor] = None
        self.error_handler: WorkflowErrorHandler = WorkflowErrorHandler()

    @track_tokens(node_type="workflow")
    async def generate(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Execute the adaptive workflow"""
        tracer = get_tracer(self.context)

        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.generate"
        ) as span:
            objective = "<unknown>"  # Initialize with default value
            try:
                # Extract objective
                objective = await self._extract_objective(message)
                span.set_attribute("workflow.objective", objective[:200])

                # Execute workflow
                result = await self._execute_workflow(objective, request_params, span)

                # Record metrics
                span.set_attribute("workflow.success", result.success)
                span.set_attribute("workflow.iterations", result.iterations)
                span.set_attribute("workflow.total_cost", result.total_cost)

                return self._format_result_as_messages(result)

            except Exception as e:
                # Enhanced error handling
                await self.error_handler.handle_error(
                    error=e,
                    workflow_stage="main_execution",
                    context={
                        "objective": objective,
                        "execution_id": self._current_execution_id,
                    },
                )

                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

                # Add error summary to span
                span.set_attribute(
                    "workflow.error_summary", self.error_handler.create_debug_report()
                )

                raise

    async def _execute_workflow(
        self,
        objective: str,
        request_params: Optional[RequestParams],
        span: trace.Span,
    ) -> ExecutionResult:
        """Main workflow execution following Deep Research pattern"""
        execution_id = str(uuid.uuid4())
        self._current_execution_id = execution_id

        # Initialize enhanced memory
        self._current_memory = EnhancedExecutionMemory(
            execution_id=execution_id,
            objective=objective,
            start_time=datetime.now(timezone.utc),
        )

        # Initialize new components
        self.knowledge_extractor = KnowledgeExtractor(self.llm_factory, self.context)
        self.action_controller = ActionController()
        self.budget_manager = BudgetManager(
            token_budget=self.token_budget,
            time_budget=self.time_budget,
            cost_budget=self.cost_budget,
            iteration_budget=self.max_iterations,
        )
        logger.debug(
            f"Created BudgetManager - time_budget: {self.time_budget}, cost_budget: {self.cost_budget}"
        )

        # Phase 1: Initial Analysis
        span.add_event("phase_1_initial_analysis")
        task_type = await self._analyze_objective(objective, span)
        self._current_memory.task_type = task_type

        # Initialize subtask queue with original objective
        self.subtask_queue = AdaptiveSubtaskQueue(objective, task_type)

        # Record initial analysis action
        await self.action_controller.record_action(
            WorkflowAction.ANALYZE,
            True,
            context={
                "task_type": task_type.value,
                "iteration": 0,  # Initial analysis happens before iterations start
            },
        )

        # Main iterative loop
        start_time = time.time()

        while await self._should_continue(start_time) and self.subtask_queue.has_next():
            iteration = self._current_memory.iterations + 1
            self._current_memory.iterations = iteration
            await self.budget_manager.increment_iteration()
            await self.action_controller.update_iteration(iteration)

            # Update budget manager with actual token usage from TokenCounter
            if self.context and self.context.token_counter:
                # Get current token usage from the tree
                current_path = self.context.token_counter.get_current_path()
                if current_path:
                    # Get summary to find total usage so far
                    summary = self.context.token_counter.get_summary()
                    total_tokens = summary.usage.total_tokens
                    total_cost = summary.cost

                    logger.debug(
                        f"Syncing budget with token counter - tokens: {total_tokens}, cost: ${total_cost}"
                    )
                    await self.budget_manager.set_absolute_usage(
                        total_tokens, total_cost
                    )

                    # Also update memory for tracking
                    self._current_memory.context_tokens = total_tokens
                    self._current_memory.total_cost = total_cost

            # Check for beast mode
            if await self.budget_manager.should_enter_beast_mode():
                logger.warning("Entering beast mode due to resource constraints")
                return await self._beast_mode_completion(objective, span)

            # Get next subtask from queue
            current_subtask = await self.subtask_queue.get_next()
            if not current_subtask:
                logger.info("No more subtasks in queue")
                break

            span.add_event(
                f"iteration_{iteration}_start",
                {
                    "subtask": current_subtask.aspect.name,
                    "depth": current_subtask.depth,
                    "knowledge_items": len(self._current_memory.knowledge_items),
                    "cost_so_far": self._current_memory.total_cost,
                },
            )

            # Check if this subtask needs decomposition
            if await self._needs_decomposition(current_subtask):
                # Phase 2: Plan Research for complex subtask
                aspects = await self._plan_research_for_subtask(current_subtask, span)
                if aspects:
                    # Add new aspects to queue
                    added = await self.subtask_queue.add_subtasks(
                        aspects, current_subtask.aspect.objective, current_subtask.depth
                    )
                    logger.info(f"Added {added} new subtasks to queue")
                    await self._current_memory.add_action(
                        "decompose",
                        {"subtask": current_subtask.aspect.name, "new_subtasks": added},
                    )
                    continue

            # Phase 3: Execute single subtask
            try:
                result = await self._execute_single_subtask(
                    current_subtask, request_params, span
                )

                # Validate result if enabled
                if self.enable_validation and result.success:
                    await self._validate_subagent_result(result, objective)

                # Extract knowledge from result
                if result.success and result.findings:
                    knowledge_items = await self.knowledge_extractor.extract_knowledge(
                        result, {"objective": objective}
                    )
                    await self._current_memory.add_knowledge_items(knowledge_items)
                    logger.info(f"Extracted {len(knowledge_items)} knowledge items")

                # Mark subtask as completed
                await self.subtask_queue.mark_completed(current_subtask)
                await self.budget_manager.record_action_success(
                    BudgetActionType.RESEARCH
                )

            except Exception as e:
                # Enhanced error handling with context
                _error_context = await self.error_handler.handle_error(
                    error=e,
                    workflow_stage="subtask_execution",
                    context={
                        "iteration": iteration,
                        "subtask_name": current_subtask.aspect.name,
                        "subtask_depth": current_subtask.depth,
                        "agent_name": current_subtask.aspect.use_predefined_agent
                        or f"Aspect - {current_subtask.aspect.name}",
                    },
                )

                # Still log for immediate visibility (error handler logs too but with more context)
                logger.error(
                    f"Failed to execute subtask {current_subtask.aspect.name}: {e}",
                    exc_info=True,  # Include traceback
                )

                current_subtask.last_error = str(e)
                await self.budget_manager.record_action_failure(
                    BudgetActionType.RESEARCH, str(e)
                )

                # Try to requeue if not too many attempts
                if await self.subtask_queue.requeue_failed(current_subtask):
                    logger.info(
                        f"Requeued failed subtask {current_subtask.aspect.name}"
                    )
                else:
                    logger.warning(
                        f"Subtask {current_subtask.aspect.name} permanently failed"
                    )

            # Check context window usage before synthesis
            await self._check_and_manage_context_window()

            # Phase 4: Periodically synthesize accumulated knowledge
            if (
                iteration % self.synthesis_frequency == 0
                and len(self._current_memory.knowledge_items)
                >= self.min_knowledge_for_synthesis
            ):
                synthesis_messages = await self._synthesize_accumulated_knowledge(span)
                self._current_memory.research_history.append(synthesis_messages)

                # Phase 5: Decide if we should conclude
                decision = await self._decide_next_steps(synthesis_messages, span)
                if decision.is_complete:
                    logger.info("Research objective achieved")
                    break

            # Save checkpoint
            await self.memory_manager.save_memory(self._current_memory)

        # Phase 6: Generate Final Report
        span.add_event("phase_6_final_report")
        final_report = await self._generate_final_report(span)

        # Create result
        total_time = time.time() - start_time

        # Get final token usage and cost from TokenCounter
        final_cost = self._current_memory.total_cost
        total_tokens = 0
        input_tokens = 0
        output_tokens = 0

        if self.context and self.context.token_counter:
            summary = self.context.token_counter.get_summary()
            final_cost = summary.cost
            total_tokens = summary.usage.total_tokens
            input_tokens = summary.usage.input_tokens
            output_tokens = summary.usage.output_tokens

        result = ExecutionResult(
            execution_id=execution_id,
            objective=objective,
            task_type=task_type,
            result_messages=final_report,
            confidence=0.9,
            iterations=self._current_memory.iterations,
            subagents_used=len(self._current_memory.subagent_results),
            total_time_seconds=total_time,
            total_cost=final_cost,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=True,
        )

        return result

    async def _analyze_objective(self, objective: str, span: trace.Span) -> TaskType:
        """Analyze the objective to determine task type"""
        # Create analysis agent
        analyzer = Agent(
            name="ObjectiveAnalyzer",
            instruction=LEAD_RESEARCHER_ANALYZE_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(analyzer)

        from pydantic import BaseModel

        class Analysis(BaseModel):
            task_type: TaskType
            key_aspects: List[str]
            estimated_scope: str

        analysis = await llm.generate_structured(
            message=f"Analyze this objective: {objective}",
            response_model=Analysis,
        )

        span.add_event("objective_analyzed", {"task_type": analysis.task_type})
        return analysis.task_type

    async def _plan_research(self, span: trace.Span) -> List[ResearchAspect]:
        """Plan what aspects to research next"""
        # Check context window before planning
        await self._check_and_manage_context_window()

        # Build context from memory
        context = self._build_context()

        # Use lead researcher to identify aspects
        lead_agent = Agent(
            name="LeadResearcher",
            instruction=LEAD_RESEARCHER_PLAN_PROMPT,
            context=self.context,
            model_preferences=self.model_preferences,  # Use consistent model preferences
        )
        llm = self.llm_factory(lead_agent)

        from pydantic import BaseModel, Field

        class ResearchPlan(BaseModel):
            aspects: List[ResearchAspect] = Field(max_length=5)
            rationale: str

        plan = await llm.generate_structured(
            message=f"{context}\n\nWhat aspects should we investigate next?",
            response_model=ResearchPlan,
        )

        span.add_event("research_planned", {"aspects": len(plan.aspects)})
        return plan.aspects

    async def _execute_research(
        self,
        aspects: List[ResearchAspect],
        request_params: Optional[RequestParams],
        span: trace.Span,
    ) -> List[SubagentResult]:
        """Execute research using subagents"""
        span.add_event("research_execution_start", {"aspects": len(aspects)})

        if self.enable_parallel and len(aspects) > 1:
            # Execute in parallel
            tasks = []
            for aspect in aspects:
                task = self._execute_single_aspect(aspect, request_params, span)
                tasks.append(task)

            results = await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            results = []
            for aspect in aspects:
                result = await self._execute_single_aspect(aspect, request_params, span)
                results.append(result)

        return results

    async def _needs_decomposition(self, subtask: SubtaskQueueItem) -> bool:
        """Determine if a subtask needs to be broken down further"""
        # Don't decompose if already deep in the tree
        if subtask.depth >= self.max_subtask_depth:
            return False

        # Don't decompose if it's a simple lookup or direct question
        if subtask.aspect.use_predefined_agent:
            return False

        # Use LLM to assess complexity
        complexity_agent = Agent(
            name="ComplexityAssessor",
            instruction="Assess if this research aspect needs to be broken down into smaller parts.",
            context=self.context,
        )
        llm = self.llm_factory(complexity_agent)

        from pydantic import BaseModel

        class ComplexityAssessment(BaseModel):
            needs_decomposition: bool
            reason: str
            estimated_subtasks: int = 0

        try:
            assessment = await llm.generate_structured(
                message=f"Should this research aspect be broken down? Aspect: {subtask.aspect.name}, Objective: {subtask.aspect.objective}",
                response_model=ComplexityAssessment,
            )

            return assessment.needs_decomposition and assessment.estimated_subtasks > 1
        except Exception:
            # Default to not decomposing on error
            return False

    async def _plan_research_for_subtask(
        self, subtask: SubtaskQueueItem, span: trace.Span
    ) -> List[ResearchAspect]:
        """Plan research specifically for a subtask"""
        # Build focused context
        context = f"""
<adaptive:planning-context>
    <adaptive:current-subtask>
        <adaptive:name>{subtask.aspect.name}</adaptive:name>
        <adaptive:objective>{subtask.aspect.objective}</adaptive:objective>
        <adaptive:depth>{subtask.depth}</adaptive:depth>
    </adaptive:current-subtask>
    
    <adaptive:accumulated-knowledge>
{
            self.knowledge_extractor.format_knowledge_for_context(
                await self._current_memory.get_relevant_knowledge(
                    subtask.aspect.objective, limit=5
                )
            )
        }
    </adaptive:accumulated-knowledge>
    
    <adaptive:available-mcp-servers>{
            ", ".join(self.available_servers)
        }</adaptive:available-mcp-servers>
</adaptive:planning-context>"""

        # Use lead researcher to identify aspects
        lead_agent = Agent(
            name="SubtaskPlanner",
            instruction=LEAD_RESEARCHER_PLAN_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(lead_agent)

        from pydantic import BaseModel, Field

        class SubtaskPlan(BaseModel):
            aspects: List[ResearchAspect] = Field(
                max_length=3
            )  # Limit for focused decomposition
            rationale: str

        plan = await llm.generate_structured(
            message=f"{context}\n\nBreak down this subtask into 2-3 focused research aspects.",
            response_model=SubtaskPlan,
        )

        span.add_event(
            "subtask_decomposed",
            {"subtask": subtask.aspect.name, "aspects": len(plan.aspects)},
        )
        return plan.aspects

    async def _execute_single_subtask(
        self,
        subtask: SubtaskQueueItem,
        request_params: Optional[RequestParams],
        span: trace.Span,
    ) -> SubagentResult:
        """Execute a single subtask from the queue"""
        # This is essentially the old _execute_single_aspect but adapted for subtasks
        aspect = subtask.aspect
        result = SubagentResult(
            aspect_name=aspect.name,
            start_time=datetime.now(timezone.utc),
        )

        try:
            # Record action start
            action_start = time.time()
            await self._current_memory.add_action(
                "execute_subtask",
                {"name": aspect.name, "depth": subtask.depth},
                success=True,
            )

            # Check if we should use a predefined agent
            if (
                aspect.use_predefined_agent
                and aspect.use_predefined_agent in self.available_agents
            ):
                agent = self.available_agents[aspect.use_predefined_agent]
                logger.info(f"Using predefined agent: {aspect.use_predefined_agent}")
                use_predefined = True
            else:
                # Create new agent
                if self._current_memory.task_type == TaskType.RESEARCH:
                    template = RESEARCH_SUBAGENT_TEMPLATE
                else:
                    template = ACTION_SUBAGENT_TEMPLATE

                instruction = template.format(
                    aspect=aspect.name,
                    objective=aspect.objective,
                    tools=", ".join(aspect.required_servers)
                    if aspect.required_servers
                    else "standard tools",
                )

                agent = Agent(
                    name=f"Subagent_{aspect.name.replace(' ', '_')}",
                    instruction=instruction,
                    server_names=aspect.required_servers,
                    context=self.context,
                )
                use_predefined = False

            # Execute with the agent
            if use_predefined and isinstance(agent, AugmentedLLM):
                llm = agent

                # Track whether we pushed to token counter
                pushed_token_context = False

                try:
                    # Push a context for this specific subtask to track its tokens
                    if self.context and self.context.token_counter:
                        self.context.token_counter.push(
                            name=f"subtask_{aspect.name}",
                            node_type="agent",
                            metadata={"aspect": aspect.name, "depth": subtask.depth},
                        )
                        pushed_token_context = True
                    # Execute with limited iterations
                    params = RequestParams(
                        max_iterations=5,
                        parallel_tool_calls=True,
                    )
                    if request_params:
                        params = params.model_copy(
                            update=request_params.model_dump(exclude_unset=True)
                        )

                    # Execute research
                    response = await llm.generate_str(
                        message=f"Research: {aspect.objective}",
                        request_params=params,
                    )

                    result.findings = response
                    result.success = True
                    result.end_time = datetime.now(timezone.utc)

                finally:
                    # Pop and capture token usage for this subtask
                    if (
                        pushed_token_context
                        and self.context
                        and self.context.token_counter
                    ):
                        subtask_node = self.context.token_counter.pop()
                        if subtask_node:
                            usage = subtask_node.aggregate_usage()
                            result.input_tokens = usage.input_tokens
                            result.output_tokens = usage.output_tokens
                            result.total_tokens = usage.total_tokens

                            # Get model info from the usage
                            if usage.model_name:
                                result.model_name = usage.model_name
                            if usage.model_info:
                                result.provider = usage.model_info.provider

                            # Calculate cost
                            if usage.model_name:
                                result.cost = self.context.token_counter.calculate_cost(
                                    model_name=usage.model_name,
                                    input_tokens=usage.input_tokens,
                                    output_tokens=usage.output_tokens,
                                    provider=result.provider,
                                )
            else:
                async with agent:
                    if isinstance(agent, Agent):
                        llm = await agent.attach_llm(self.llm_factory)
                    else:
                        llm = agent

                    # Track whether we pushed to token counter
                    pushed_token_context = False

                    try:
                        # Push a context for this specific subtask to track its tokens
                        if self.context and self.context.token_counter:
                            self.context.token_counter.push(
                                name=f"subtask_{aspect.name}",
                                node_type="agent",
                                metadata={
                                    "aspect": aspect.name,
                                    "depth": subtask.depth,
                                },
                            )
                            pushed_token_context = True
                        # Execute with limited iterations
                        params = RequestParams(
                            max_iterations=5,
                            parallel_tool_calls=True,
                        )
                        if request_params:
                            params = params.model_copy(
                                update=request_params.model_dump(exclude_unset=True)
                            )

                        # Execute research
                        response = await llm.generate_str(
                            message=f"Research: {aspect.objective}",
                            request_params=params,
                        )

                        result.findings = response
                        result.success = True
                        result.end_time = datetime.now(timezone.utc)

                    finally:
                        # Pop and capture token usage for this subtask
                        if (
                            pushed_token_context
                            and self.context
                            and self.context.token_counter
                        ):
                            subtask_node = self.context.token_counter.pop()
                            if subtask_node:
                                usage = subtask_node.aggregate_usage()
                                result.input_tokens = usage.input_tokens
                                result.output_tokens = usage.output_tokens
                                result.total_tokens = usage.total_tokens

                                # Get model info from the usage
                                if usage.model_name:
                                    result.model_name = usage.model_name
                                if usage.model_info:
                                    result.provider = usage.model_info.provider

                                # Calculate cost
                                if usage.model_name:
                                    result.cost = (
                                        self.context.token_counter.calculate_cost(
                                            model_name=usage.model_name,
                                            input_tokens=usage.input_tokens,
                                            output_tokens=usage.output_tokens,
                                            provider=result.provider,
                                        )
                                    )

            # Update metrics
            duration = time.time() - action_start
            if self.action_controller:
                await self.action_controller.record_action(
                    WorkflowAction.EXECUTE_SUBTASK,
                    True,
                    duration=duration,
                    context={
                        "subtask": aspect.name,
                        "depth": subtask.depth,
                        "iteration": self._current_memory.iterations,  # Add current iteration
                    },
                )

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.end_time = datetime.now(timezone.utc)

            # Enhanced error handling
            error_context = await self.error_handler.handle_error(
                error=e,
                workflow_stage="single_subtask_execution",
                context={
                    "subtask_name": aspect.name,
                    "subtask_depth": subtask.depth,
                    "agent_name": aspect.use_predefined_agent
                    or f"Aspect - {aspect.name}",
                },
            )

            logger.error(f"Subtask {aspect.name} failed: {e}", exc_info=True)

            # Add recovery suggestion to failed attempt
            recovery_suggestions = self.error_handler.get_recovery_suggestions(
                error_context
            )
            await self._current_memory.add_failed_attempt(
                "execute_subtask",
                str(e),
                {
                    "subtask": aspect.name,
                    "recovery_suggestions": recovery_suggestions[
                        :2
                    ],  # Top 2 suggestions
                },
            )

        # Update memory - token tracking and cost are now handled by TokenCounter
        self._current_memory.subagent_results.append(result)

        return result

    async def _execute_single_aspect(
        self,
        aspect: ResearchAspect,
        request_params: Optional[RequestParams],
        span: trace.Span,
    ) -> SubagentResult:
        """Execute research for a single aspect"""
        # Create a subtask item to reuse the same execution logic
        parent_objective = (
            self._current_memory.objective
            if self._current_memory
            else "Unknown objective"
        )
        subtask_item = SubtaskQueueItem(
            aspect=aspect, depth=0, parent_objective=parent_objective
        )
        return await self._execute_single_subtask(subtask_item, request_params, span)

    async def _synthesize_results(
        self,
        results: List[SubagentResult],
        span: trace.Span,
    ) -> List[MessageT]:
        """Synthesize results from subagents"""
        # Create synthesis agent
        synthesizer = Agent(
            name="Synthesizer",
            instruction=LEAD_RESEARCHER_SYNTHESIZE_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(synthesizer)

        # Format results
        results_list = [
            f'    <adaptive:result aspect="{r.aspect_name}">\n{r.findings}\n    </adaptive:result>'
            for r in results
            if r.success and r.findings
        ]
        results_text = "\n".join(results_list)

        synthesis_messages = await llm.generate(
            message=f"""<adaptive:synthesis-request>
    <adaptive:research-findings>
{results_text}
    </adaptive:research-findings>
</adaptive:synthesis-request>

Synthesize these research findings.""",
        )

        span.add_event("results_synthesized")
        return synthesis_messages

    async def _decide_next_steps(
        self,
        synthesis_messages: List[MessageT],
        span: trace.Span,
    ) -> SynthesisDecision:
        """Decide whether to continue research or conclude"""
        # Create decision agent
        decider = Agent(
            name="DecisionMaker",
            instruction=LEAD_RESEARCHER_DECIDE_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(decider)

        # Get synthesis as string - just the last message (assistant's synthesis)
        synthesis_str = ""
        if synthesis_messages:
            synthesis_str = llm.message_str(synthesis_messages[-1], content_only=True)

        context = f"""
<adaptive:decision-context>
    <adaptive:objective>{self._current_memory.objective}</adaptive:objective>
    <adaptive:iterations-completed>{self._current_memory.iterations}</adaptive:iterations-completed>
    
    <adaptive:latest-synthesis>
{synthesis_str}
    </adaptive:latest-synthesis>
    
    <adaptive:previous-research>
{self._format_research_history()}
    </adaptive:previous-research>
</adaptive:decision-context>"""

        decision = await llm.generate_structured(
            message=context,
            response_model=SynthesisDecision,
        )

        span.add_event(
            "decision_made",
            {
                "is_complete": decision.is_complete,
                "confidence": decision.confidence,
                "new_aspects": len(decision.new_aspects) if decision.new_aspects else 0,
            },
        )

        return decision

    async def _generate_final_report(self, span: trace.Span) -> List[MessageT]:
        """Generate the final report"""
        # Create report writer
        writer = Agent(
            name="ReportWriter",
            instruction=FINAL_REPORT_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(writer)

        # Build comprehensive context
        context = f"""
<adaptive:final-report-context>
    <adaptive:objective>{self._current_memory.objective}</adaptive:objective>
    <adaptive:task-type>{self._current_memory.task_type}</adaptive:task-type>
    <adaptive:iterations>{self._current_memory.iterations}</adaptive:iterations>
    
    <adaptive:research-history>
{self._format_research_history()}
    </adaptive:research-history>
    
    <adaptive:all-findings>
{self._format_all_findings()}
    </adaptive:all-findings>
    
    <adaptive:error-summary>
{self._get_error_summary_for_report()}
    </adaptive:error-summary>
</adaptive:final-report-context>"""

        report_messages = await llm.generate(
            message=f"Generate a comprehensive report based on this research:\n\n{context}",
        )

        return report_messages

    # Helper methods
    async def _should_continue(self, start_time: float) -> bool:
        """Check if workflow should continue"""
        # If we have a budget manager, use it
        if self.budget_manager:
            should_continue, reason = await self.budget_manager.should_continue()
            if not should_continue:
                logger.info(f"Budget manager: {reason}")
            return should_continue

        # Fallback to original logic if no budget manager
        # Time check
        if time.time() - start_time > self.time_budget.total_seconds():
            logger.info("Time budget exceeded")
            return False

        # Iteration check
        if self._current_memory.iterations >= self.max_iterations:
            logger.info("Maximum iterations reached")
            return False

        # Cost check
        if self._current_memory.total_cost > self.cost_budget:
            logger.info("Cost budget exceeded")
            return False

        return True

    def _build_context(self) -> str:
        """Build context for planning"""
        # Format available agents if any
        agents_info = ""
        if self.available_agents:
            agent_list = "\n".join(
                [
                    f'        <adaptive:agent name="{agent_name}">{self._format_agent_info(agent_name)}</adaptive:agent>'
                    for agent_name in self.available_agents.keys()
                ]
            )
            agents_info = f"\n    <adaptive:available-agents>\n{agent_list}\n    </adaptive:available-agents>"

        return f"""
<adaptive:planning-context>
    <adaptive:objective>{self._current_memory.objective}</adaptive:objective>
    <adaptive:task-type>{self._current_memory.task_type}</adaptive:task-type>
    <adaptive:iterations>{self._current_memory.iterations}</adaptive:iterations>
    
    <adaptive:research-conducted>
{self._format_research_history()}
    </adaptive:research-conducted>
    
    <adaptive:available-mcp-servers>{", ".join(self.available_servers)}</adaptive:available-mcp-servers>
    {agents_info}
</adaptive:planning-context>"""

    def _format_research_history(self) -> str:
        """Format research history"""
        if not self._current_memory.research_history:
            return "No research conducted yet."

        # We need an LLM instance to convert messages to strings
        # Use a simple agent for this
        formatter = Agent(
            name="HistoryFormatter",
            instruction="Format research history",
            context=self.context,
        )
        llm = self.llm_factory(formatter)

        history_parts = []
        for i, synthesis_messages in enumerate(self._current_memory.research_history):
            if synthesis_messages:
                # Convert the last message (synthesis) to string
                synthesis_str = llm.message_str(
                    synthesis_messages[-1], content_only=True
                )
                history_parts.append(
                    f'    <adaptive:iteration number="{i + 1}">\n{synthesis_str}\n    </adaptive:iteration>'
                )

        return "\n\n".join(history_parts)

    def _format_all_findings(self) -> str:
        """Format all subagent findings"""
        findings = []
        for result in self._current_memory.subagent_results:
            if result.success and result.findings:
                findings.append(
                    f'    <adaptive:finding aspect="{result.aspect_name}">\n{result.findings}\n    </adaptive:finding>'
                )

        return "\n\n".join(findings)

    def _get_error_summary_for_report(self) -> str:
        """Get a summary of errors for the final report"""
        error_summary = self.error_handler.get_error_summary()

        if error_summary["total_errors"] == 0:
            return ""

        summary_parts = [
            "\n## Error Summary",
            f"Total errors encountered: {error_summary['total_errors']}",
            "",
        ]

        # Breakdown by category
        if error_summary["by_category"]:
            summary_parts.append("Errors by type:")
            for category, count in error_summary["by_category"].items():
                summary_parts.append(f"- {category}: {count}")
            summary_parts.append("")

        # Recent errors
        if error_summary["recent_errors"]:
            summary_parts.append("Recent errors:")
            for error in error_summary["recent_errors"][-3:]:  # Last 3
                summary_parts.append(
                    f"- [{error['severity']}] {error['message']} at {error['stage']}"
                )

        return "\n".join(summary_parts)

    async def _validate_subagent_result(
        self, result: SubagentResult, objective: str
    ) -> None:
        """
        Validate a single subagent result using EvaluatorOptimizer.
        Updates the result's confidence score and validation notes.
        """
        if not result.success or not result.findings:
            result.confidence = 0.0
            return

        # Skip validation if disabled
        if not self.enable_validation:
            return

        # For RESEARCH tasks, use a cheaper/faster validation approach
        is_research_task = self._current_memory.task_type == TaskType.RESEARCH

        try:
            # Create an evaluator agent for result validation
            evaluator_instruction = f"""You are a critical research validator. Evaluate the research result based on:
1. Factual accuracy and consistency
2. Relevance to the objective: {objective}
3. Logical coherence and supporting evidence
4. Potential hallucinations or unsupported claims

Provide specific feedback on any issues found and rate the quality."""

            evaluator = Agent(
                name="ResultValidator",
                instruction=evaluator_instruction,
                context=self.context,
            )

            # Use EvaluatorOptimizer to validate the result
            # The optimizer here is just a pass-through that returns the result
            optimizer = Agent(
                name="ResultPassthrough",
                instruction="Return the research findings as-is.",
                context=self.context,
            )

            # For RESEARCH tasks, use faster validation settings
            if is_research_task:
                validator = EvaluatorOptimizerLLM(
                    optimizer=optimizer,
                    evaluator=evaluator,
                    llm_factory=self.llm_factory,
                    min_rating=QualityRating.POOR,  # Lower bar for research validation
                    max_refinements=0,  # No refinement, just validate once
                    context=self.context,
                )
            else:
                # ACTION tasks get more thorough validation
                validator = EvaluatorOptimizerLLM(
                    optimizer=optimizer,
                    evaluator=evaluator,
                    llm_factory=self.llm_factory,
                    min_rating=QualityRating.FAIR,  # Higher quality bar
                    max_refinements=1,  # Allow one refinement pass
                    context=self.context,
                )

            # Prepare the message for validation
            validation_message = f"""Research Topic: {result.aspect_name}
            
Findings:
{result.findings}"""

            # Run validation
            _ = await validator.generate_str(
                message=validation_message,
                request_params=RequestParams(
                    temperature=0.3,  # Low temperature for consistency
                    max_iterations=1,
                ),
            )

            # Extract validation results from the evaluator's history
            if validator.refinement_history and len(validator.refinement_history) > 0:
                evaluation = validator.refinement_history[0].get("evaluation_result")
                if evaluation:
                    # Map quality rating to confidence score
                    rating_to_confidence = {
                        QualityRating.POOR: 0.25,
                        QualityRating.FAIR: 0.5,
                        QualityRating.GOOD: 0.75,
                        QualityRating.EXCELLENT: 1.0,
                    }
                    result.confidence = rating_to_confidence.get(evaluation.rating, 0.5)

                    # Add validation notes if there are issues
                    if evaluation.feedback:
                        result.validation_notes = evaluation.feedback

                    # Additional penalty for specific issues
                    if evaluation.focus_areas:
                        for area in evaluation.focus_areas:
                            if (
                                "hallucination" in area.lower()
                                or "unsupported" in area.lower()
                            ):
                                result.confidence *= 0.5
                            elif "irrelevant" in area.lower():
                                result.confidence *= 0.7

                    logger.info(
                        f"Validated {result.aspect_name}: rating={evaluation.rating}, "
                        f"confidence={result.confidence:.2f}"
                    )

        except Exception as e:
            logger.warning(f"Validation failed for {result.aspect_name}: {e}")
            # Don't fail the whole process if validation fails
            result.confidence = 0.7  # Default medium confidence

    def _get_model_context_window(
        self, model_name: Optional[str] = None, provider: Optional[str] = None
    ) -> Optional[int]:
        """Get context window size for a model"""
        if not self.context or not self.context.token_counter:
            return None

        if not model_name:
            # Try to get from current execution
            if self._current_memory and self._current_memory.subagent_results:
                # Get most recent model used
                for result in reversed(self._current_memory.subagent_results):
                    if result.model_name:
                        model_name = result.model_name
                        provider = result.provider
                        break

        if not model_name:
            return None

        model_info = self.context.token_counter.find_model_info(model_name, provider)
        return model_info.context_window if model_info else None

    def _get_context_buffer(
        self,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        buffer_percentage: float = 0.15,
    ) -> int:
        """Get the buffer size for context window management

        Args:
            model_name: The model name to check
            provider: The provider for the model
            buffer_percentage: Percentage of context window to use as buffer (default: 0.15 = 15%)

        Returns:
            Buffer size in tokens
        """
        context_window = self._get_model_context_window(model_name, provider)

        if context_window:
            # Use specified percentage of context window as buffer
            return int(context_window * buffer_percentage)

        # Default fallback buffer size
        return 10000

    async def _check_and_manage_context_window(
        self, usage_threshold: float = 0.7, target_ratio: float = 0.6
    ) -> None:
        """Check context window usage and manage memory if needed

        Args:
            usage_threshold: When to start trimming (default: 0.7 = 70% of context window)
            target_ratio: Target usage after trimming (default: 0.6 = 60% of context window)
        """
        if (
            not self.context
            or not self.context.token_counter
            or not self._current_memory
        ):
            return

        # Get the workflow's token usage
        workflow_usage = self.context.token_counter.get_workflow_usage(self.name)
        if not workflow_usage:
            return

        # Get model info for context window
        model_name = None
        provider = None
        if self._current_memory.subagent_results:
            # Get most recent model used
            for result in reversed(self._current_memory.subagent_results):
                if result.model_name:
                    model_name = result.model_name
                    provider = result.provider
                    break

        if not model_name:
            return

        context_window = self._get_model_context_window(model_name, provider)
        if not context_window:
            return

        # Calculate usage ratio
        usage_ratio = workflow_usage.total_tokens / context_window

        # If we're using more than the threshold of context window, start trimming
        if usage_ratio > usage_threshold:
            logger.warning(
                f"Context window usage high: {workflow_usage.total_tokens}/{context_window} "
                f"({usage_ratio:.1%}) for model {model_name}"
            )

            # Calculate target tokens based on target ratio
            target_tokens = int(context_window * target_ratio)

            # Use memory's trim function
            if hasattr(self._current_memory, "trim_to_token_limit"):
                (
                    items_removed,
                    tokens_saved,
                ) = await self._current_memory.trim_to_token_limit(target_tokens)
                if items_removed > 0:
                    logger.info(
                        f"Trimmed {items_removed} knowledge items to save ~{tokens_saved} tokens "
                        f"(target: {target_tokens}, model: {model_name})"
                    )

            # Also consider trimming research history if still over limit
            aggressive_threshold = (
                usage_threshold + 0.1
            )  # e.g., 0.8 if threshold is 0.7
            if (
                usage_ratio > aggressive_threshold
                and len(self._current_memory.research_history) > 2
            ):
                # Keep only the most recent synthesis
                old_count = len(self._current_memory.research_history)
                self._current_memory.research_history = (
                    self._current_memory.research_history[-2:]
                )
                logger.info(
                    f"Trimmed research history from {old_count} to {len(self._current_memory.research_history)} entries"
                )

    async def _extract_objective(self, message: Any) -> str:
        """Extract objective using the LLM for robust parsing"""
        # For simple string messages, return directly
        if isinstance(message, str):
            return message

        # For complex messages, use LLM to extract the objective
        # This handles provider-specific message formats gracefully
        try:
            # Create a simple extraction agent
            extractor = Agent(
                name="ObjectiveExtractor",
                instruction="Extract and return the user's request as a clear objective statement.",
                context=self.context,
            )

            llm = self.llm_factory(extractor)

            # Just get the objective as a string - let the Lead Researcher handle any complexity
            objective = await llm.generate_str(
                message=f"What is the user asking for in this message?\n\n{message}",
                request_params=RequestParams(max_iterations=1),
            )

            return objective

        except Exception as e:
            logger.warning(f"Failed to extract objective using LLM: {e}")
            # Fallback to string conversion
            return str(message)

    def _format_result_as_messages(self, result: ExecutionResult) -> List[MessageT]:
        """Format workflow result as messages"""
        # Return the stored messages directly
        return result.result_messages

    def _format_agent_info(self, agent_name: str) -> str:
        """Format agent information for display to Lead Researcher"""
        agent = self.available_agents.get(agent_name)
        if not agent:
            return f"{agent_name} (not found)"

        # Get agent details
        if isinstance(agent, AugmentedLLM):
            name = agent.agent.name
            instruction = agent.agent.instruction
            server_names = agent.agent.server_names
        elif isinstance(agent, Agent):
            name = agent.name
            instruction = agent.instruction
            server_names = agent.server_names
        else:
            return f"{agent_name} (unknown type)"

        # Format server list
        servers_str = ", ".join(server_names) if server_names else "no specific servers"

        return f"{name}: {instruction} (servers: {servers_str})"

    async def generate_str(
        self,
        message: MessageTypes,
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_str"
        ) as span:
            span.set_attribute("agent.name", self.agent.name)

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            result = await self.generate(
                message=message,
                request_params=params,
            )

            res = str(result[0]) if result else ""
            span.set_attribute("result", res)

            return res

    async def generate_structured(
        self,
        message: MessageTypes,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Request a structured LLM generation and return the result as a Pydantic model."""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_structured"
        ) as span:
            span.set_attribute("agent.name", self.agent.name)

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            result_str = await self.generate_str(message=message, request_params=params)

            llm: AugmentedLLM = self.llm_factory(
                agent=Agent(
                    name="Structured Output",
                    instruction="Produce a structured output given a message",
                    context=self.context,
                )
            )

            structured_result = await llm.generate_structured(
                message=result_str,
                response_model=response_model,
                request_params=params,
            )

            if self.context.tracing_enabled:
                try:
                    span.set_attribute(
                        "structured_response_json", structured_result.model_dump_json()
                    )
                except Exception:
                    # Ignore serialization errors
                    pass

            return structured_result

    async def _synthesize_accumulated_knowledge(
        self, span: trace.Span
    ) -> List[MessageT]:
        """Synthesize accumulated knowledge items into insights"""
        # Create synthesis agent
        synthesizer = Agent(
            name="KnowledgeSynthesizer",
            instruction=LEAD_RESEARCHER_SYNTHESIZE_PROMPT,
            context=self.context,
        )
        llm = self.llm_factory(synthesizer)

        # Format knowledge for synthesis
        knowledge_text = self.knowledge_extractor.format_knowledge_for_context(
            self._current_memory.knowledge_items[-20:],  # Last 20 items
            group_by_type=True,
        )

        synthesis_prompt = f"""
<adaptive:synthesis-request>
    <adaptive:objective>{self._current_memory.objective}</adaptive:objective>
    
    <adaptive:accumulated-knowledge>
{knowledge_text}
    </adaptive:accumulated-knowledge>
    
    <adaptive:progress>
        <adaptive:iterations>{self._current_memory.iterations}</adaptive:iterations>
        <adaptive:subtasks-completed>{len(self.subtask_queue.completed_subtasks)}</adaptive:subtasks-completed>
        <adaptive:subtasks-remaining>{len(self.subtask_queue.queue)}</adaptive:subtasks-remaining>
    </adaptive:progress>
</adaptive:synthesis-request>

Synthesize the accumulated knowledge into key insights and findings."""

        synthesis_messages = await llm.generate(message=synthesis_prompt)

        span.add_event(
            "knowledge_synthesized",
            {"knowledge_items": len(self._current_memory.knowledge_items)},
        )

        return synthesis_messages

    async def _beast_mode_completion(
        self, objective: str, span: trace.Span
    ) -> ExecutionResult:
        """
        Force completion when resources are exhausted.
        Uses dramatic prompting to overcome LLM hesitation.
        """
        span.add_event("beast_mode_activated")

        # Prepare comprehensive context
        knowledge_summary = self.knowledge_extractor.format_knowledge_for_context(
            self._current_memory.knowledge_items, group_by_type=True
        )

        completed_subtasks = "\n".join(
            [
                f"- {item.aspect.name} (depth: {item.depth})"
                for item in self.subtask_queue.completed_subtasks[-10:]
            ]
        )

        failed_subtasks = self.subtask_queue.get_failed_summary()

        beast_context = f"""
{BEAST_MODE_PROMPT}

<adaptive:objective>{objective}</adaptive:objective>

<adaptive:accumulated-knowledge>
{knowledge_summary}
</adaptive:accumulated-knowledge>

<adaptive:completed-subtasks>
{completed_subtasks}
</adaptive:completed-subtasks>

<adaptive:failed-attempts>
{failed_subtasks}
{self._current_memory.get_failed_attempts_summary()}
</adaptive:failed-attempts>

<adaptive:research-history>
{self._format_research_history()}
</adaptive:research-history>
"""

        # Create high-urgency agent
        beast_agent = Agent(
            name="BeastModeResolver",
            instruction="You MUST provide the best possible answer based on available information. Acknowledge limitations but DO NOT refuse to answer.",
            context=self.context,
        )

        llm = self.llm_factory(beast_agent)

        try:
            # Get forced response
            response_messages = await llm.generate(
                message=beast_context,
                request_params=RequestParams(
                    temperature=self.beast_mode_temperature,  # Higher temp for creativity
                    max_iterations=1,  # No multi-step reasoning
                ),
            )

            # Create result with limitations noted
            return ExecutionResult(
                execution_id=self._current_execution_id,
                objective=objective,
                task_type=self._current_memory.task_type,
                result_messages=response_messages,
                confidence=0.7,  # Lower confidence
                iterations=self._current_memory.iterations,
                subagents_used=len(self._current_memory.subagent_results),
                total_time_seconds=time.time()
                - self._current_memory.start_time.timestamp(),
                total_cost=self._current_memory.total_cost,
                success=True,
                limitations=[
                    "Resource limits reached - answer based on partial information",
                    f"Processed {len(self.subtask_queue.completed_subtasks)} subtasks",
                    f"Failed to complete {len(self.subtask_queue.failed_subtasks)} subtasks",
                ],
            )

        except Exception as e:
            logger.error(f"Beast mode failed: {e}")
            # Emergency fallback
            return await self._emergency_response(objective, str(e))

    async def _emergency_response(self, objective: str, error: str) -> ExecutionResult:
        """Provide emergency response when all else fails"""
        emergency_prompt = f"""
EMERGENCY RESPONSE REQUIRED

Objective: {objective}

System Error: {error}

Based on any partial knowledge available, provide your best attempt at an answer.
If no knowledge is available, acknowledge the limitation and suggest what the user should try.

Available Knowledge Summary:
- Knowledge items collected: {len(self._current_memory.knowledge_items)}
- Subtasks completed: {len(self.subtask_queue.completed_subtasks) if self.subtask_queue else 0}
- Subtasks failed: {len(self.subtask_queue.failed_subtasks) if self.subtask_queue else 0}

Provide a helpful response despite the technical difficulties.
"""

        try:
            emergency_agent = Agent(
                name="EmergencyResponder",
                instruction="Provide helpful response even with limited information.",
                context=self.context,
            )
            llm = self.llm_factory(emergency_agent)

            response_messages = await llm.generate(message=emergency_prompt)

            return ExecutionResult(
                execution_id=self._current_execution_id,
                objective=objective,
                task_type=self._current_memory.task_type or TaskType.RESEARCH,
                result_messages=response_messages,
                confidence=0.3,
                iterations=self._current_memory.iterations,
                subagents_used=len(self._current_memory.subagent_results),
                total_time_seconds=time.time()
                - self._current_memory.start_time.timestamp(),
                total_cost=self._current_memory.total_cost,
                success=False,
                limitations=[
                    f"System error occurred: {error}",
                    "Emergency response based on minimal information",
                ],
            )
        except Exception as e2:
            # Absolute last resort - create minimal agent for error message
            logger.error(f"Emergency response also failed: {e2}")

            try:
                error_agent = Agent(
                    name="ErrorReporter",
                    instruction="Report critical system error to user.",
                    context=self.context,
                )
                error_llm = self.llm_factory(error_agent)

                error_messages = await error_llm.generate(
                    message=f"❌ I encountered a critical error while researching '{objective}': {error}. "
                    f"Additional error in emergency response: {e2}. "
                    f"Please try rephrasing your question or check your configuration."
                )

                return ExecutionResult(
                    execution_id=self._current_execution_id,
                    objective=objective,
                    task_type=TaskType.RESEARCH,
                    result_messages=error_messages,
                    confidence=0.0,
                    iterations=self._current_memory.iterations,
                    subagents_used=0,
                    total_time_seconds=0,
                    total_cost=0,
                    success=False,
                    limitations=["Critical system failure"],
                )
            except:
                # If even that fails, we have to give up and re-raise
                raise
