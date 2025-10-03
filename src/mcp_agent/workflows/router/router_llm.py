from typing import Callable, List, Literal, Optional, TYPE_CHECKING

from opentelemetry import trace
from pydantic import BaseModel

from mcp_agent.agents.agent import Agent
from mcp_agent.tracing.semconv import GEN_AI_REQUEST_TOP_K
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
    RequestParams,
    ModelT,
)
from mcp_agent.workflows.router.router_base import ResultT, Router, RouterResult
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)

ROUTING_SYSTEM_INSTRUCTION = """
You are a highly accurate request router that directs incoming requests to the most appropriate category.
A category is a specialized destination, such as a Function, an MCP Server (a collection of tools/functions), or an Agent (a collection of servers).
You will be provided with a request and a list of categories to choose from.
You can choose one or more categories, or choose none if no category is appropriate.
"""


DEFAULT_ROUTING_INSTRUCTION = """
You are a highly accurate request router that directs incoming requests to the most appropriate category.
A category is a specialized destination, such as a Function, an MCP Server (a collection of tools/functions), or an Agent (a collection of servers).
Below are the available routing categories, each with their capabilities and descriptions:

{context}

Your task is to analyze the following request and determine the most appropriate categories from the options above. Consider:
- The specific capabilities and tools each destination offers
- How well the request matches the category's description
- Whether the request might benefit from multiple categories (up to {top_k})

Request: {request}

Respond in JSON format:
{{
    "categories": [
        {{
            "category": <category name>,
            "confidence": <high, medium or low>,
            "reasoning": <brief explanation>
        }}
    ]
}}

Only include categories that are truly relevant. You may return fewer than {top_k} if appropriate.
If none of the categories are relevant, return an empty list.
"""


class LLMRouterResult(RouterResult[ResultT]):
    """A class that represents the result of an LLMRouter.route request"""

    confidence: Literal["high", "medium", "low"]
    """The confidence level of the routing decision."""

    reasoning: str | None = None
    """
    A brief explanation of the routing decision.
    This is optional and may only be provided if the router is an LLM
    """


class StructuredResponseCategory(BaseModel):
    """A class that represents a single category returned by an LLM router"""

    category: str
    """The name of the category (i.e. MCP server, Agent or function) to route the input to."""

    confidence: Literal["high", "medium", "low"]
    """The confidence level of the routing decision."""

    reasoning: str | None = None
    """A brief explanation of the routing decision."""


class StructuredResponse(BaseModel):
    """A class that represents the structured response of an LLM router"""

    categories: List[StructuredResponseCategory]
    """A list of categories to route the input to."""


class LLMRouter(Router, AugmentedLLM[MessageParamT, MessageT]):
    """
    A router that uses an LLM to route an input to a specific category.

    Exposes:
    - route/route_to_* APIs that return routing targets.
    - As an AugmentedLLM: generate/generate_str/generate_structured delegate to routing
      and return the routing outputs in unstructured or structured forms, enabling
      composition with other AugmentedLLM-based workflows (Parallel, Evaluator/Optimizer, etc.).
    """

    def __init__(
        self,
        name: str | None = None,
        llm_factory: Callable[[Agent], AugmentedLLM] | None = None,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        routing_instruction: str | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        # Cooperative super init: Router gets routing params; AugmentedLLM gets name/instruction
        router_name = f"{name}-router" if name else None
        super().__init__(
            server_names=server_names,
            agents=agents,
            functions=functions,
            routing_instruction=routing_instruction,
            context=context,
            name=router_name,
            instruction="You are a router workflow that returns categories.",
            **kwargs,
        )

        # Factory to create downstream LLMs for routed agents
        if llm_factory is None:
            raise ValueError("llm_factory must be provided to LLMRouter")
        self.llm_factory: Callable[[Agent], AugmentedLLM] = llm_factory

        # Create the classifier LLM used to make routing decisions via factory
        classifier_agent = Agent(
            name=f"{name}-classifier" if name else "router-classifier",
            instruction=ROUTING_SYSTEM_INSTRUCTION,
        )
        try:
            self.classifier_llm: AugmentedLLM = self.llm_factory(
                agent=classifier_agent,
                instruction=ROUTING_SYSTEM_INSTRUCTION,
                context=context,
            )
            if getattr(self.classifier_llm, "instruction", None) in (None, ""):
                setattr(self.classifier_llm, "instruction", ROUTING_SYSTEM_INSTRUCTION)
        except TypeError:
            self.classifier_llm = self.llm_factory(classifier_agent)

        # Back-compat alias for introspection
        self.llm: AugmentedLLM = self.classifier_llm

    @classmethod
    async def create(
        cls,
        name: str | None = None,
        llm_factory: Callable[[Agent], AugmentedLLM] | None = None,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        routing_instruction: str | None = None,
        context: Optional["Context"] = None,
    ) -> "LLMRouter":
        """
        Factory method to create and initialize a router.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            name=name,
            llm_factory=llm_factory,
            server_names=server_names,
            agents=agents,
            functions=functions,
            routing_instruction=routing_instruction,
            context=context,
        )
        await instance.initialize()
        return instance

    async def route(
        self, request: str, top_k: int = 1
    ) -> List[LLMRouterResult[str | Agent | AugmentedLLM | Callable]]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(f"{self.__class__.__name__}.route") as span:
            self._annotate_span_for_route_request(span, request, top_k)

            if not self.initialized:
                await self.initialize()

            res = await self._route_with_llm(request, top_k)
            self._annotate_span_for_router_result(span, res)
            return res

    async def route_to_server(
        self, request: str, top_k: int = 1
    ) -> List[LLMRouterResult[str]]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.route_to_server"
        ) as span:
            self._annotate_span_for_route_request(span, request, top_k)

            if not self.initialized:
                await self.initialize()

            res = await self._route_with_llm(
                request,
                top_k,
                include_servers=True,
                include_agents=False,
                include_functions=False,
            )
            self._annotate_span_for_router_result(span, res)
            return res

    async def route_to_agent(
        self, request: str, top_k: int = 1
    ) -> List[LLMRouterResult[Agent | AugmentedLLM]]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.route_to_agent"
        ) as span:
            self._annotate_span_for_route_request(span, request, top_k)

            if not self.initialized:
                await self.initialize()

            res = await self._route_with_llm(
                request,
                top_k,
                include_servers=False,
                include_agents=True,
                include_functions=False,
            )
            self._annotate_span_for_router_result(span, res)
            return res

    async def route_to_function(
        self, request: str, top_k: int = 1
    ) -> List[LLMRouterResult[Callable]]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.route_to_function"
        ) as span:
            self._annotate_span_for_route_request(span, request, top_k)

            if not self.initialized:
                await self.initialize()

            res = await self._route_with_llm(
                request,
                top_k,
                include_servers=False,
                include_agents=False,
                include_functions=True,
            )
            self._annotate_span_for_router_result(span, res)
            return res

    # region AugmentedLLM interface

    @track_tokens(node_type="agent")
    async def generate(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> List[MessageT]:
        """Delegate generation to the routed agent/LLM and return its response."""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.generate"
        ) as span:
            # Build a routing string from the provided message
            routing_text = self._normalize_message_to_text(message)
            self._annotate_span_for_route_request(span, routing_text, top_k=1)

            # Select the best downstream agent/LLM
            delegate_llm = await self._select_delegate_llm(routing_text, span)

            # Delegate the call with the original message and return downstream results
            return (
                await delegate_llm.generate(message)
                if request_params is None
                else await delegate_llm.generate(message, request_params)
            )  # type: ignore[return-value]

    @track_tokens(node_type="agent")
    async def generate_str(
        self,
        message: str | MessageParamT | List[MessageParamT],
        request_params: RequestParams | None = None,
    ) -> str:
        """Delegate to the routed agent/LLM and return its string response."""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.generate_str"
        ) as span:
            routing_text = self._normalize_message_to_text(message)
            self._annotate_span_for_route_request(span, routing_text, top_k=1)

            delegate_llm = await self._select_delegate_llm(routing_text, span)
            return (
                await delegate_llm.generate_str(message)
                if request_params is None
                else await delegate_llm.generate_str(message, request_params)
            )

    @track_tokens(node_type="agent")
    async def generate_structured(
        self,
        message: str | MessageParamT | List[MessageParamT],
        response_model: type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """Delegate to the routed agent/LLM and return its structured response."""
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.generate_structured"
        ) as span:
            routing_text = self._normalize_message_to_text(message)
            self._annotate_span_for_route_request(span, routing_text, top_k=1)

            delegate_llm = await self._select_delegate_llm(routing_text, span)
            return (
                await delegate_llm.generate_structured(message, response_model)
                if request_params is None
                else await delegate_llm.generate_structured(
                    message, response_model, request_params
                )
            )

    # endregion

    async def _route_with_llm(
        self,
        request: str,
        top_k: int = 1,
        include_servers: bool = True,
        include_agents: bool = True,
        include_functions: bool = True,
    ) -> List[LLMRouterResult]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}._route_with_llm"
        ) as span:
            self._annotate_span_for_route_request(span, request, top_k)

            if not self.initialized:
                await self.initialize()

            routing_instruction = (
                self.routing_instruction or DEFAULT_ROUTING_INSTRUCTION
            )

            # Generate the categories context
            context = self._generate_context(
                include_servers=include_servers,
                include_agents=include_agents,
                include_functions=include_functions,
            )

            # logger.debug(
            #     f"Requesting routing from LLM, \nrequest: {request} \ntop_k: {top_k} \nrouting_instruction: {routing_instruction} \ncontext={context}",
            #     data={"progress_action": "Routing", "agent_name": "LLM Router"},
            # )

            # Format the prompt with all the necessary information
            prompt = routing_instruction.format(
                context=context, request=request, top_k=top_k
            )

            # Get routes from the inner/classifier LLM
            response = await self.classifier_llm.generate_structured(
                message=prompt,
                response_model=StructuredResponse,
            )

            if self.context.tracing_enabled:
                response_categories_data = {}
                for i, r in enumerate(response.categories):
                    response_categories_data[f"category.{i}.category"] = r.category
                    response_categories_data[f"category.{i}.confidence"] = r.confidence
                    if r.reasoning:
                        response_categories_data[f"category.{i}.reasoning"] = (
                            r.reasoning
                        )

                span.add_event(
                    "routing.response",
                    {
                        "prompt": prompt,
                        **response_categories_data,
                    },
                )

            # logger.debug(
            #     "Routing Response received",
            #     data={"progress_action": "Finished", "agent_name": "LLM Router"},
            # )

            # Construct the result
            if not response or not response.categories:
                return []

            result: List[LLMRouterResult] = []
            for r in response.categories:
                router_category = self.categories.get(r.category)
                if not router_category:
                    # Skip invalid categories
                    # TODO: saqadri - log or raise an error
                    continue

                result.append(
                    LLMRouterResult(
                        result=router_category.category,
                        confidence=r.confidence,
                        reasoning=r.reasoning,
                    )
                )

            self._annotate_span_for_router_result(span, result)

            return result[:top_k]

    def _annotate_span_for_route_request(
        self,
        span: trace.Span,
        request: str,
        top_k: int,
    ):
        """Annotate the span with the request and top_k."""
        if not self.context.tracing_enabled:
            return
        span.set_attribute("request", request)
        span.set_attribute(GEN_AI_REQUEST_TOP_K, top_k)
        if getattr(self.classifier_llm, "name", None):
            span.set_attribute("llm", self.classifier_llm.name)
        span.set_attribute(
            "agents", [a.name for a in self.agents] if self.agents else []
        )
        span.set_attribute("servers", self.server_names or [])
        span.set_attribute(
            "functions", [f.__name__ for f in self.functions] if self.functions else []
        )

    def _annotate_span_for_router_result(
        self,
        span: trace.Span,
        result: List[LLMRouterResult],
    ):
        """Annotate the span with the router result."""
        if not self.context.tracing_enabled:
            return
        for i, res in enumerate(result):
            span.set_attribute(f"result.{i}.confidence", res.confidence)
            if res.reasoning:
                span.set_attribute(f"result.{i}.reasoning", res.reasoning)
            if res.p_score:
                span.set_attribute(f"result.{i}.p_score", res.p_score)

            result_key = f"result.{i}.result"
            if isinstance(res.result, str):
                span.set_attribute(result_key, res.result)
            elif isinstance(res.result, Agent):
                span.set_attribute(result_key, res.result.name)
            elif callable(res.result):
                span.set_attribute(result_key, res.result.__name__)

    def _generate_context(
        self,
        include_servers: bool = True,
        include_agents: bool = True,
        include_functions: bool = True,
    ) -> str:
        """Generate a formatted context list of categories."""

        context_list = []
        idx = 1

        # Format all categories
        if include_servers:
            for category in self.server_categories.values():
                context_list.append(self.format_category(category, idx))
                idx += 1

        if include_agents:
            for category in self.agent_categories.values():
                context_list.append(self.format_category(category, idx))
                idx += 1

        if include_functions:
            for category in self.function_categories.values():
                context_list.append(self.format_category(category, idx))
                idx += 1

        return "\n\n".join(context_list)

    def _normalize_message_to_text(
        self, message: str | MessageParamT | List[MessageParamT]
    ) -> str:
        """Convert incoming message(s) to a routing text string.

        This ensures compatibility across heterogeneous LLM MessageParam types.
        """
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            parts: List[str] = []
            for m in message:
                try:
                    parts.append(self.message_param_str(m))
                except Exception:
                    parts.append(str(m))
            return "\n\n".join(parts)
        try:
            return self.message_param_str(message)
        except Exception:
            return str(message)

    async def _select_delegate_llm(
        self, routing_text: str, span: trace.Span | None = None
    ) -> AugmentedLLM:
        """Route to an agent and return its attached LLM for delegation."""
        results = await self.route_to_agent(request=routing_text, top_k=1)
        if not results:
            raise ValueError("Router did not find a suitable agent for this request")

        target = results[0].result

        # The base router stores Agents as categories. If an AugmentedLLM was
        # directly provided as an agent in a subclass, handle that here too.
        delegate_llm: AugmentedLLM | None = None
        if isinstance(target, AugmentedLLM):
            delegate_llm = target
        elif isinstance(target, Agent):
            # Attach a new LLM to the agent; wrap factory to inject context when supported
            def _factory_with_context(agent: Agent, **kw):
                try:
                    llm = self.llm_factory(agent=agent, context=self.context, **kw)
                    return llm
                except TypeError:
                    return self.llm_factory(agent)

            delegate_llm = await target.attach_llm(llm_factory=_factory_with_context)

        if span and self.context.tracing_enabled:
            span.add_event(
                "router.generate.delegated",
                {
                    "delegate.type": (
                        "llm" if isinstance(target, AugmentedLLM) else "agent"
                    ),
                    "delegate.name": (
                        target.name
                        if isinstance(target, Agent)
                        else getattr(target, "name", "")
                    ),
                },
            )

        logger.info(f"Routing to agent {target.name}")

        if not isinstance(delegate_llm, AugmentedLLM) or delegate_llm is None:
            raise ValueError(
                "Selected agent does not have an attached LLM to delegate generation"
            )

        return delegate_llm
