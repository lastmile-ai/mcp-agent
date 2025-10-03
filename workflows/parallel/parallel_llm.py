from typing import Any, Callable, List, Optional, Type, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.tracing.semconv import GEN_AI_AGENT_NAME
from mcp_agent.tracing.telemetry import (
    get_tracer,
    record_attributes,
    serialize_attributes,
)
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
    ModelT,
    RequestParams,
)
from mcp_agent.workflows.parallel.fan_in import FanInInput, FanIn
from mcp_agent.workflows.parallel.fan_out import FanOut

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class ParallelLLM(AugmentedLLM[MessageParamT, MessageT]):
    """
    LLMs can sometimes work simultaneously on a task (fan-out)
    and have their outputs aggregated programmatically (fan-in).
    This workflow performs both the fan-out and fan-in operations using  LLMs.
    From the user's perspective, an input is specified and the output is returned.

    When to use this workflow:
        Parallelization is effective when the divided subtasks can be parallelized
        for speed (sectioning), or when multiple perspectives or attempts are needed for
        higher confidence results (voting).

    Examples:
        Sectioning:
            - Implementing guardrails where one model instance processes user queries
            while another screens them for inappropriate content or requests.

            - Automating evals for evaluating LLM performance, where each LLM call
            evaluates a different aspect of the model’s performance on a given prompt.

        Voting:
            - Reviewing a piece of code for vulnerabilities, where several different
            agents review and flag the code if they find a problem.

            - Evaluating whether a given piece of content is inappropriate,
            with multiple agents evaluating different aspects or requiring different
            vote thresholds to balance false positives and negatives.
    """

    def __init__(
        self,
        fan_in_agent: Agent | AugmentedLLM | Callable[[FanInInput], Any],
        fan_out_agents: List[Agent | AugmentedLLM] | None = None,
        fan_out_functions: List[Callable] | None = None,
        name: str | None = None,
        llm_factory: Callable[[Agent], AugmentedLLM] = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        """
        Initialize the LLM with a list of server names and an instruction.
        If a name is provided, it will be used to identify the LLM.
        If an agent is provided, all other properties are optional
        """
        super().__init__(
            name=name,
            instruction="You are a parallel LLM workflow that can fan-out to multiple LLMs and fan-in to an aggregator LLM.",
            context=context,
            **kwargs,
        )

        self.llm_factory = llm_factory
        self.fan_in_agent = fan_in_agent
        self.fan_out_agents = fan_out_agents
        self.fan_out_functions = fan_out_functions
        self.history = (
            None  # History tracking is complex in this workflow, so it is not supported
        )

        self.fan_in_fn: Callable[[FanInInput], Any] = None
        self.fan_in: FanIn = None
        if isinstance(fan_in_agent, Callable):
            self.fan_in_fn = fan_in_agent
        else:
            self.fan_in = FanIn(
                aggregator_agent=fan_in_agent,
                llm_factory=llm_factory,
                context=context,
            )

        self.fan_out = FanOut(
            agents=fan_out_agents,
            functions=fan_out_functions,
            llm_factory=llm_factory,
            context=context,
        )

    @track_tokens(node_type="agent")
    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT] | Any:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.{self.name}.generate"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
                self._annotate_span_for_generation_message(span, message)
                if request_params:
                    AugmentedLLM.annotate_span_with_request_params(span, request_params)

            # First, we fan-out
            responses = await self.fan_out.generate(
                message=message,
                request_params=request_params,
            )

            if self.context.tracing_enabled:
                for agent_name, fan_out_responses in responses.items():
                    res_attributes = {}
                    for i, res in enumerate(fan_out_responses):
                        try:
                            res_dict = (
                                res if isinstance(res, dict) else res.model_dump()
                            )
                            res_attributes.update(
                                serialize_attributes(res_dict, f"response.{i}")
                            )
                        # pylint: disable=broad-exception-caught
                        except Exception:
                            # Just no-op, best-effort tracing
                            continue
                    span.add_event(f"fan_out.{agent_name}.responses", res_attributes)

            # Then, we fan-in
            if self.fan_in_fn:
                result = await self.fan_in_fn(responses)
            else:
                result = await self.fan_in.generate(
                    messages=responses,
                    request_params=request_params,
                )

            if self.context.tracing_enabled:
                try:
                    if isinstance(result, list):
                        for i, res in enumerate(result):
                            res_dict = (
                                res if isinstance(res, dict) else res.model_dump()
                            )
                            record_attributes(span, res_dict, f"response.{i}")
                    else:
                        res_dict = (
                            result if isinstance(result, dict) else result.model_dump()
                        )
                        record_attributes(span, res_dict, "response")
                # pylint: disable=broad-exception-caught
                except Exception:
                    # Just no-op, best-effort tracing
                    pass

            return result

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
            if self.context.tracing_enabled:
                span.set_attribute(GEN_AI_AGENT_NAME, self.agent.name)
                self._annotate_span_for_generation_message(span, message)
                if request_params:
                    AugmentedLLM.annotate_span_with_request_params(span, request_params)

            # First, we fan-out
            responses = await self.fan_out.generate(
                message=message,
                request_params=request_params,
            )

            if self.context.tracing_enabled:
                for agent_name, fan_out_responses in responses.items():
                    res_attributes = {}
                    for i, res in enumerate(fan_out_responses):
                        try:
                            res_dict = (
                                res if isinstance(res, dict) else res.model_dump()
                            )
                            res_attributes.update(
                                serialize_attributes(res_dict, f"response.{i}")
                            )
                        # pylint: disable=broad-exception-caught
                        except Exception:
                            # Just no-op, best-effort tracing
                            continue
                    span.add_event(f"fan_out.{agent_name}.responses", res_attributes)

            # Then, we fan-in
            if self.fan_in_fn:
                result = str(await self.fan_in_fn(responses))
            else:
                result = await self.fan_in.generate_str(
                    messages=responses,
                    request_params=request_params,
                )
            span.set_attribute("response", result)
            return result

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
            if self.context.tracing_enabled:
                self._annotate_span_for_generation_message(span, message)
                span.set_attribute(
                    "response_model",
                    f"{response_model.__module__}.{response_model.__name__}",
                )
                if request_params:
                    AugmentedLLM.annotate_span_with_request_params(span, request_params)

            # First, we fan-out
            responses = await self.fan_out.generate(
                message=message,
                request_params=request_params,
            )

            if self.context.tracing_enabled:
                for agent_name, fan_out_responses in responses.items():
                    res_attributes = {}
                    for i, res in enumerate(fan_out_responses):
                        try:
                            res_dict = (
                                res if isinstance(res, dict) else res.model_dump()
                            )
                            res_attributes.update(
                                serialize_attributes(res_dict, f"response.{i}")
                            )
                        # pylint: disable=broad-exception-caught
                        except Exception:
                            # Just no-op, best-effort tracing
                            continue
                    span.add_event(f"fan_out.{agent_name}.responses", res_attributes)

            # Then, we fan-in
            if self.fan_in_fn:
                result = await self.fan_in_fn(responses)
            else:
                result = await self.fan_in.generate_structured(
                    messages=responses,
                    response_model=response_model,
                    request_params=request_params,
                )

            if self.context.tracing_enabled:
                try:
                    span.set_attribute(
                        "structured_response_json", result.model_dump_json()
                    )
                # pylint: disable=broad-exception-caught
                except Exception:
                    pass  # Just no-op, best-effort tracing

            return result
