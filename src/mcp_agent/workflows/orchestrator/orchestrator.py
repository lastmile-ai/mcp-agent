from abc import abstractmethod
import contextlib
from dataclasses import dataclass
from typing import (
    Callable,
    Coroutine,
    List,
    Literal,
    Optional,
    Protocol,
    Type,
    TYPE_CHECKING,
)

from mcp_agent.agents.agent import Agent
from mcp_agent.tracing.semconv import GEN_AI_AGENT_NAME
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
    ModelT,
    RequestParams,
)
from mcp_agent.workflows.orchestrator.orchestrator_models import (
    format_plan_result,
    format_step_result,
    NextStep,
    Plan,
    PlanResult,
    Step,
    StepResult,
    TaskWithResult,
)
from mcp_agent.workflows.orchestrator.orchestrator_prompts import (
    FULL_PLAN_PROMPT_TEMPLATE,
    ITERATIVE_PLAN_PROMPT_TEMPLATE,
    SYNTHESIZE_PLAN_PROMPT_TEMPLATE,
    TASK_PROMPT_TEMPLATE,
)
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class GetFullPlanPrompt(Protocol):
    """Protocol for getting the full plan prompt"""

    @abstractmethod
    def __call__(
        self, objective: str, plan_result: PlanResult, agents: List[Agent]
    ) -> str:
        """Get the full plan prompt for the given objective, plan result, and agents"""
        ...


class GetIterativePlanPrompt(Protocol):
    """Protocol for getting the iterative plan prompt"""

    @abstractmethod
    def __call__(
        self, objective: str, plan_result: PlanResult, agents: List[Agent]
    ) -> str:
        """Get the iterative plan prompt for the given objective, plan result, and agents"""
        ...


class GetTaskPrompt(Protocol):
    """Protocol for getting the task prompt"""

    @abstractmethod
    def __call__(self, objective: str, task: str, context: str) -> str:
        """Get the task prompt for the given objective, task, and context"""
        ...


class GetSynthesizePlanPrompt(Protocol):
    """Protocol for getting the synthesize plan prompt"""

    @abstractmethod
    def __call__(self, plan_result: PlanResult) -> str:
        """Get the synthesize plan prompt for the given plan result"""
        ...


@dataclass
class OrchestratorOverrides:
    """Configuration overrides for Orchestrator behavior and prompts"""

    orchestrator_instruction: str | None = None
    """Override the main orchestrator LLM's system instruction"""

    planner_instruction: str | None = None
    """Override the planner agent's instruction (used to break down tasks into steps)"""

    synthesizer_instruction: str | None = None
    """Override the synthesizer agent's instruction (used to combine results into final output)"""

    get_full_plan_prompt: GetFullPlanPrompt | None = None
    """Get prompt to generate the full plan of action"""

    get_iterative_plan_prompt: GetIterativePlanPrompt | None = None
    """Get prompt to generate the next step of action"""

    get_task_prompt: GetTaskPrompt | None = None
    """Get prompt to specify as system instruction for a subtask in the plan"""

    get_synthesize_plan_prompt: GetSynthesizePlanPrompt | None = None
    """Get prompt to synthesize the orchestration of the workflow into a final response"""


class Orchestrator(AugmentedLLM[MessageParamT, MessageT]):
    """
    In the orchestrator-workers workflow, a central planner LLM dynamically breaks down tasks,
    delegates them to worker LLMs, and synthesizes their results. It does this
    in a loop until the task is complete.

    When to use this workflow:
        - This workflow is well-suited for complex tasks where you can’t predict the
        subtasks needed (in coding, for example, the number of files that need to be
        changed and the nature of the change in each file likely depend on the task).

    Example where orchestrator-workers is useful:
        - Coding products that make complex changes to multiple files each time.
        - Search tasks that involve gathering and analyzing information from multiple sources
        for possible relevant information.
    """

    def __init__(
        self,
        llm_factory: Callable[[Agent], AugmentedLLM[MessageParamT, MessageT]],
        name: str | None = None,
        planner: Agent | AugmentedLLM | None = None,
        synthesizer: Agent | AugmentedLLM | None = None,
        available_agents: List[Agent | AugmentedLLM] | None = None,
        plan_type: Literal["full", "iterative"] = "full",
        overrides: OrchestratorOverrides | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        """
        Args:
            llm_factory: Factory function to create an LLM for a given agent
            planner: LLM to use for planning steps (if not provided, a default planner will be used)
            plan_type: "full" planning generates the full plan first, then executes. "iterative" plans the next step, and loops until success.
            available_agents: List of agents available to tasks executed by this orchestrator
            context: Application context
            overrides: Optional overrides for instructions and prompt templates
        """
        self.overrides = overrides or OrchestratorOverrides()

        orchestrator_instruction = (
            self.overrides.orchestrator_instruction
            or "You are an orchestrator-worker LLM that breaks down tasks into subtasks, delegates them to worker LLMs, and synthesizes their results."
        )

        super().__init__(
            name=name,
            instruction=orchestrator_instruction,
            context=context,
            **kwargs,
        )

        self.llm_factory = llm_factory

        planner_instruction = (
            self.overrides.planner_instruction
            or """
            You are an expert planner. Given an objective task and a list of MCP servers (which are collections of tools)
            or Agents (which are collections of servers), your job is to break down the objective into a series of steps,
            which can be performed by LLMs with access to the servers or agents.
            """
        )

        if planner is not None:
            if isinstance(planner, Agent):
                self.planner = llm_factory(planner)
            else:
                self.planner = planner
        else:
            self.planner = llm_factory(
                agent=Agent(
                    name="LLM Orchestration Planner",
                    instruction=planner_instruction,
                )
            )

        if synthesizer is not None:
            if isinstance(synthesizer, Agent):
                self.synthesizer = llm_factory(synthesizer)
            else:
                self.synthesizer = synthesizer
        else:
            synthesizer_instruction = (
                self.overrides.synthesizer_instruction
                or "You are an expert at synthesizing the results of a plan into a single coherent message."
            )

            self.synthesizer = llm_factory(
                agent=Agent(
                    name="LLM Orchestration Synthesizer",
                    instruction=synthesizer_instruction,
                )
            )

        if plan_type not in ["full", "iterative"]:
            raise ValueError("plan_type must be 'full' or 'iterative'")
        else:
            self.plan_type: Literal["full", "iterative"] = plan_type

        self.server_registry = self.context.server_registry
        self.agents = {agent.name: agent for agent in available_agents or []}

        self.default_request_params = self.default_request_params or RequestParams(
            # History tracking is not yet supported for orchestrator workflows
            use_history=False,
            # We set a higher default maxTokens value to allow for longer responses
            maxTokens=16384,
        )

    @track_tokens(node_type="agent")
    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Request an LLM generation, which may run multiple iterations, and return the result"""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            span.set_attribute("plan_type", self.plan_type)
            span.set_attribute("available_agents", list(self.agents.keys()))

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            # TODO: saqadri - history tracking is complicated in this multi-step workflow, so we will ignore it for now
            if params.use_history:
                raise NotImplementedError(
                    "History tracking is not yet supported for orchestrator workflows"
                )

            objective = str(message)
            plan_result = await self.execute(objective=objective, request_params=params)

            if self.context.tracing_enabled:
                span.set_attribute("is_complete", plan_result.is_complete)
                span.set_attribute("objective", plan_result.objective)
                if plan_result.plan:
                    for idx, step in enumerate(plan_result.plan.steps):
                        span.set_attribute(
                            f"plan.steps.{idx}.description", step.description
                        )
                        for tidx, task in enumerate(step.tasks):
                            span.set_attribute(
                                f"plan.steps.{idx}.tasks.{tidx}.description",
                                task.description,
                            )
                            span.set_attribute(
                                f"plan.steps.{idx}.tasks.{tidx}.agent", task.agent
                            )
                for idx, step_result in enumerate(plan_result.step_results):
                    span.set_attribute(
                        f"plan.step_results.{idx}.step.description",
                        step_result.step.description,
                    )
                    for tidx, task_result in enumerate(step_result.task_results):
                        span.set_attribute(
                            f"plan.step_results.{idx}.task_results.{tidx}.description",
                            task_result.description,
                        )
                        span.set_attribute(
                            f"plan.step_results.{idx}.task_results.{tidx}.result",
                            task_result.result,
                        )
                if plan_result.result is not None:
                    span.set_attribute("result", plan_result.result)

            return [plan_result.result]

    async def generate_str(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> str:
        """Request an LLM generation and return the string representation of the result"""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_str"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            span.set_attribute("plan_type", self.plan_type)

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            result = await self.generate(
                message=message,
                request_params=params,
            )

            res = str(result[0])
            span.set_attribute("result", res)

            return res

    async def generate_structured(
        self,
        message: str | MessageParamT | List[MessageParamT],
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Request a structured LLM generation and return the result as a Pydantic model."""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate_structured"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            span.set_attribute("plan_type", self.plan_type)

            params = self.get_request_params(request_params)

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            result_str = await self.generate_str(message=message, request_params=params)

            llm: AugmentedLLM = self.llm_factory(
                agent=Agent(
                    name="Structured Output",
                    instruction="Produce a structured output given a message",
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
                # pylint: disable=broad-exception-caught
                except Exception:
                    span.set_attribute("unstructured_response", result_str)

            return structured_result

    async def execute(
        self, objective: str, request_params: RequestParams | None = None
    ) -> PlanResult:
        """Execute task with result chaining between steps"""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.execute"
        ) as span:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
            span.set_attribute("available_agents", list(self.agents.keys()))
            span.set_attribute("objective", objective)
            span.set_attribute("plan_type", self.plan_type)

            iterations = 0
            params = self.get_request_params(
                request_params,
                default=RequestParams(
                    use_history=False, max_iterations=30, maxTokens=16384
                ),
            )

            if self.context.tracing_enabled:
                AugmentedLLM.annotate_span_with_request_params(span, params)

            plan_result = PlanResult(objective=objective, step_results=[])

            while iterations < params.max_iterations:
                if self.plan_type == "iterative":
                    # Get next plan/step
                    next_step = await self._get_next_step(
                        objective=objective,
                        plan_result=plan_result,
                        request_params=params,
                    )
                    logger.debug(
                        f"Iteration {iterations}: Iterative plan:", data=next_step
                    )
                    plan = Plan(steps=[next_step], is_complete=next_step.is_complete)

                    if self.context.tracing_enabled:
                        next_step_tasks_event_data = {}
                        for idx, task in enumerate(next_step.tasks):
                            next_step_tasks_event_data[f"tasks.{idx}.description"] = (
                                task.description
                            )
                            next_step_tasks_event_data[f"tasks.{idx}.agent"] = (
                                task.agent
                            )

                        span.add_event(
                            f"plan.iterative.{iterations}",
                            {
                                "is_complete": next_step.is_complete,
                                "description": next_step.description,
                                **next_step_tasks_event_data,
                            },
                        )
                elif self.plan_type == "full":
                    plan = await self._get_full_plan(
                        objective=objective,
                        plan_result=plan_result,
                        request_params=params,
                    )
                    logger.debug(f"Iteration {iterations}: Full Plan:", data=plan)

                    if self.context.tracing_enabled:
                        plan_steps_event_data = {}
                        for idx, step in enumerate(plan.steps):
                            plan_steps_event_data[f"steps.{idx}.description"] = (
                                step.description
                            )
                            for tidx, task in enumerate(step.tasks):
                                plan_steps_event_data[
                                    f"steps.{idx}.tasks.{tidx}.description"
                                ] = task.description
                                plan_steps_event_data[
                                    f"steps.{idx}.tasks.{tidx}.agent"
                                ] = task.agent
                        span.add_event(
                            f"plan.full.{iterations}",
                            {
                                "is_complete": plan.is_complete,
                                **plan_steps_event_data,
                            },
                        )
                else:
                    raise ValueError(f"Invalid plan type {self.plan_type}")

                plan_result.plan = plan

                if plan.is_complete:
                    plan_result.is_complete = True

                    # Synthesize final result into a single message
                    synthesis_prompt: str
                    if self.overrides.get_synthesize_plan_prompt:
                        synthesis_prompt = self.overrides.get_synthesize_plan_prompt(
                            plan_result=plan_result
                        )
                    else:
                        synthesis_prompt = SYNTHESIZE_PLAN_PROMPT_TEMPLATE.format(
                            plan_result=format_plan_result(plan_result)
                        )

                    plan_result.result = await self.synthesizer.generate_str(
                        message=synthesis_prompt,
                        request_params=params.model_copy(update={"max_iterations": 1}),
                    )

                    span.set_attribute("plan.is_complete", plan_result.is_complete)
                    span.set_attribute("plan.result", plan_result.result)

                    return plan_result

                # Execute each step, collecting results
                # Note that in iterative mode this will only be a single step
                for idx, step in enumerate(plan.steps):
                    step_result = await self._execute_step(
                        step=step,
                        previous_result=plan_result,
                        request_params=params,
                    )

                    plan_result.add_step_result(step_result)

                    if self.context.tracing_enabled:
                        step_result_event_data = {
                            f"step_results.{idx}.result": step_result.result,
                            f"step_results.{idx}.description": step_result.step.description,
                        }
                        for tidx, task_result in enumerate(step_result.task_results):
                            step_result_event_data[
                                f"step_results.{idx}.task_results.{tidx}.description"
                            ] = task_result.description
                            step_result_event_data[
                                f"step_results.{idx}.task_results.{tidx}.result"
                            ] = task_result.result
                        span.add_event(
                            f"plan.{iterations}.step.{idx}.result",
                            step_result_event_data,
                        )

                logger.debug(
                    f"Iteration {iterations}: Intermediate plan result:",
                    data=plan_result,
                )
                iterations += 1

            raise RuntimeError(
                f"Task failed to complete in {params.max_iterations} iterations"
            )

    async def _execute_step(
        self,
        step: Step,
        previous_result: PlanResult,
        request_params: RequestParams | None = None,
    ) -> StepResult:
        """Execute a step's subtasks in parallel and synthesize results"""
        params = self.get_request_params(request_params)
        step_result = StepResult(step=step, task_results=[])

        # Format previous results
        context = format_plan_result(previous_result)

        # Execute subtasks in parallel
        futures: list[Coroutine[any, any, str]] = []
        results = []

        async with contextlib.AsyncExitStack() as stack:
            active_agents: dict[str, Agent] = {}

            # Set up all the tasks with their agents and LLMs
            for task in step.tasks:
                agent = self.agents.get(task.agent)
                if not agent:
                    # TODO: saqadri - should we fail the entire workflow in this case?
                    raise ValueError(
                        f'The planner created a task to "{task.description}" but there isn\'t an agent suitable for the task, consider adding an agent.'
                    )
                elif isinstance(agent, AugmentedLLM):
                    llm = agent
                else:
                    ctx_agent = active_agents.get(agent.name)
                    if ctx_agent is None:
                        ctx_agent = await stack.enter_async_context(
                            agent
                        )  # Enter agent context if agent is not already active
                        active_agents[agent.name] = ctx_agent
                    llm = await ctx_agent.attach_llm(self.llm_factory)

                task_description: str
                if self.overrides.get_task_prompt:
                    task_description = self.overrides.get_task_prompt(
                        objective=previous_result.objective,
                        task=task.description,
                        context=context,
                    )
                else:
                    task_description = TASK_PROMPT_TEMPLATE.format(
                        objective=previous_result.objective,
                        task=task.description,
                        context=context,
                    )

                futures.append(
                    llm.generate_str(
                        message=task_description,
                        request_params=params,
                    )
                )

            # Wait for all tasks to complete
            if futures:
                results = await self.executor.execute_many(futures)

        # Store task results
        for task, result in zip(step.tasks, results):
            step_result.add_task_result(
                TaskWithResult(**task.model_dump(), result=str(result))
            )

        # Synthesize overall step result
        # TODO: saqadri - instead of running through an LLM,
        # we set the step result to the formatted results of the subtasks
        # From empirical evidence, running it through an LLM at this step can
        # lead to compounding errors since some information gets lost in the synthesis
        # synthesis_prompt = SYNTHESIZE_STEP_PROMPT_TEMPLATE.format(
        #     step_result=format_step_result(step_result)
        # )
        # synthesizer_llm = self.llm_factory(
        #     agent=Agent(
        #         name="Synthesizer",
        #         instruction="Your job is to concatenate the results of parallel tasks into a single result.",
        #     )
        # )
        # step_result.result = await synthesizer_llm.generate_str(
        #     message=synthesis_prompt,
        #     max_iterations=1,
        #     model=model,
        #     stop_sequences=stop_sequences,
        #     max_tokens=max_tokens,
        # )
        step_result.result = format_step_result(step_result)

        return step_result

    async def _get_full_plan(
        self,
        objective: str,
        plan_result: PlanResult,
        request_params: RequestParams | None = None,
    ) -> Plan:
        """Generate full plan considering previous results"""

        params = self.get_request_params(request_params)

        agents = "\n".join(
            [
                f"{idx}. {self._format_agent_info(agent)}"
                for idx, agent in enumerate(self.agents, 1)
            ]
        )

        prompt: str
        if self.overrides.get_full_plan_prompt:
            prompt = self.overrides.get_full_plan_prompt(
                objective=objective, plan_result=plan_result, agents=agents
            )
        else:
            prompt = FULL_PLAN_PROMPT_TEMPLATE.format(
                objective=objective,
                plan_result=format_plan_result(plan_result),
                agents=agents,
            )

        plan = await self.planner.generate_structured(
            message=prompt,
            response_model=Plan,
            request_params=params,
        )

        return plan

    async def _get_next_step(
        self,
        objective: str,
        plan_result: PlanResult,
        request_params: RequestParams | None = None,
    ) -> NextStep:
        """Generate just the next needed step"""

        agents = "\n".join(
            [
                f"{idx}. {self._format_agent_info(agent)}"
                for idx, agent in enumerate(self.agents, 1)
            ]
        )

        prompt: str
        if self.overrides.get_iterative_plan_prompt:
            prompt = self.overrides.get_iterative_plan_prompt(
                objective=objective, plan_result=plan_result, agents=agents
            )
        else:
            prompt = ITERATIVE_PLAN_PROMPT_TEMPLATE.format(
                objective=objective,
                plan_result=format_plan_result(plan_result),
                agents=agents,
            )

        next_step = await self.planner.generate_structured(
            message=prompt,
            response_model=NextStep,
            request_params=request_params,
        )
        return next_step

    def _format_server_info(self, server_name: str) -> str:
        """Format server information for display to planners"""
        server_config = self.server_registry.get_server_config(server_name)
        server_str = f"Server Name: {server_name}"
        if not server_config:
            return server_str

        description = server_config.description
        if description:
            server_str = f"{server_str}\nDescription: {description}"

        return server_str

    def _format_agent_info(self, agent_name: str) -> str:
        """Format Agent information for display to planners"""
        agent = self.agents.get(agent_name)
        if not agent:
            return ""

        if isinstance(agent, AugmentedLLM):
            server_names = agent.agent.server_names
        elif isinstance(agent, Agent):
            server_names = agent.server_names
        else:
            logger.warning(
                f"_format_agent_info: Agent {agent_name} is not an instance of Agent or AugmentedLLM. Skipping."
            )
            return ""

        servers = "\n".join(
            [
                f"- {self._format_server_info(server_name)}"
                for server_name in server_names
            ]
        )

        return f"Agent Name: {agent.name}\nDescription: {agent.instruction}\nServers in Agent: {servers}"
