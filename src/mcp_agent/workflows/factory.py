from __future__ import annotations

from typing import Any, Callable, List, Literal, Sequence, Tuple
import os
import re
import json
import importlib
from glob import glob

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.embedding.embedding_base import EmbeddingModel
from mcp_agent.workflows.intent_classifier.intent_classifier_embedding import (
    EmbeddingIntentClassifier,
)
from mcp_agent.workflows.intent_classifier.intent_classifier_llm import (
    LLMIntentClassifier,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from mcp_agent.workflows.router.router_embedding import EmbeddingRouter
from mcp_agent.workflows.router.router_llm import LLMRouter
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.workflows.parallel.fan_in import FanInInput
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
)
from mcp_agent.workflows.orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorOverrides,
)
from mcp_agent.workflows.deep_orchestrator.config import DeepOrchestratorConfig
from mcp_agent.workflows.deep_orchestrator.orchestrator import DeepOrchestrator
from mcp_agent.workflows.swarm.swarm import Swarm, SwarmAgent
from mcp_agent.workflows.intent_classifier.intent_classifier_base import Intent
from mcp.types import ModelPreferences

# TODO: saqadri - move this to agents/factory.py

SupportedLLMProviders = Literal[
    "openai", "anthropic", "azure", "google", "bedrock", "ollama"
]
SupportedRoutingProviders = Literal["openai", "anthropic"]
SupportedEmbeddingProviders = Literal["openai", "cohere"]


def create_agent(spec: AgentSpec, context: Context | None = None) -> Agent:
    return agent_from_spec(spec, context=context)


def agent_from_spec(spec: AgentSpec, context: Context | None = None) -> Agent:
    return Agent(
        name=spec.name,
        instruction=spec.instruction,
        server_names=spec.server_names or [],
        functions=getattr(spec, "functions", []),
        connection_persistence=spec.connection_persistence,
        human_input_callback=(
            getattr(spec, "human_input_callback", None)
            or (context.human_input_handler if context else None)
        ),
        context=context,
    )


def create_llm(
    agent_name: str,
    server_names: List[str] | None = None,
    instruction: str | None = None,
    provider: str = "openai",
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
) -> AugmentedLLM:
    agent = agent_from_spec(
        AgentSpec(
            name=agent_name, instruction=instruction, server_names=server_names or []
        ),
        context=context,
    )
    factory = _llm_factory(
        provider=provider, model=model, request_params=request_params, context=context
    )
    return factory(agent=agent)


async def create_router_llm(
    *,
    server_names: List[str] | None = None,
    agents: List[AgentSpec | Agent | AugmentedLLM] | None = None,
    functions: List[Callable] | None = None,
    routing_instruction: str | None = None,
    name: str | None = None,
    provider: SupportedRoutingProviders = "openai",
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
    **kwargs,
) -> LLMRouter:
    """
    A router that uses an LLM to route requests to appropriate categories.
    This class helps to route an input to a specific MCP server, an Agent (an aggregation of MCP servers),
    or a function (any Callable).

    A router is also an AugmentedLLM, so if you call router.generate(...), it will route the input to the
    agent that is the best match for the input.

    Args:
        provider: The provider to use for the embedding router.
        model: The model to use for the embedding router.
        server_names: The server names to add to the routing categories.
        agents: The agents to add to the routing categories.
        functions: The functions to add to the routing categories.
        context: The context to use for the embedding router.
    """
    request_params = _merge_model_preferences(
        provider=provider, model=model, request_params=request_params, context=context
    )

    normalized_agents: List[Agent] = []
    for a in agents or []:
        if isinstance(a, AgentSpec):
            normalized_agents.append(agent_from_spec(a, context=context))
        elif isinstance(a, Agent | AugmentedLLM):
            normalized_agents.append(a)
        else:
            raise ValueError(f"Unsupported agent type: {type(a)}")

    if provider.lower() == "openai":
        from mcp_agent.workflows.router.router_llm_openai import OpenAILLMRouter

        return await OpenAILLMRouter.create(
            name=name,
            server_names=server_names,
            agents=normalized_agents,
            functions=functions,
            routing_instruction=routing_instruction,
            request_params=request_params,
            context=context,
            **kwargs,
        )
    elif provider.lower() == "anthropic":
        from mcp_agent.workflows.router.router_llm_anthropic import AnthropicLLMRouter

        return await AnthropicLLMRouter.create(
            name=name,
            server_names=server_names,
            agents=normalized_agents,
            functions=functions,
            routing_instruction=routing_instruction,
            request_params=request_params,
            context=context,
            **kwargs,
        )
    else:
        raise ValueError(
            f"Unsupported routing provider: {provider}. Currently supported providers are: ['openai', 'anthropic']. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
        )


async def create_router_embedding(
    *,
    provider: SupportedEmbeddingProviders = "openai",
    model: EmbeddingModel | None = None,
    server_names: List[str] | None = None,
    agents: List[AgentSpec | Agent | AugmentedLLM] | None = None,
    functions: List[Callable] | None = None,
    context: Context | None = None,
) -> EmbeddingRouter:
    """
    A router that uses embedding similarity to route requests to appropriate categories.
    This class helps to route an input to a specific MCP server, an Agent (an aggregation of MCP servers),
    or a function (any Callable).

    A router is also an AugmentedLLM, so if you call router.generate(...), it will route the input to the
    agent that is the best match for the input.

    Args:
        provider: The provider to use for the embedding router.
        model: The model to use for the embedding router.
        server_names: The server names to add to the routing categories.
        agents: The agents to add to the routing categories.
        functions: The functions to add to the routing categories.
        context: The context to use for the embedding router.
    """
    normalized_agents: List[Agent | AugmentedLLM] = []
    for a in agents or []:
        if isinstance(a, AgentSpec):
            normalized_agents.append(agent_from_spec(a, context=context))
        elif isinstance(a, Agent | AugmentedLLM):
            normalized_agents.append(a)
        else:
            raise ValueError(f"Unsupported agent type: {type(a)}")

    prov = provider.lower()
    if prov == "openai":
        from mcp_agent.workflows.router.router_embedding_openai import (
            OpenAIEmbeddingRouter,
        )

        return await OpenAIEmbeddingRouter.create(
            embedding_model=model,
            server_names=server_names,
            agents=normalized_agents,
            functions=functions,
            context=context,
        )
    if prov == "cohere":
        from mcp_agent.workflows.router.router_embedding_cohere import (
            CohereEmbeddingRouter,
        )

        return await CohereEmbeddingRouter.create(
            embedding_model=model,
            server_names=server_names,
            agents=normalized_agents,
            functions=functions,
            context=context,
        )

    raise ValueError(
        f"Unsupported embedding provider: {provider}. Currently supported providers are: ['openai', 'cohere']. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
    )


def create_orchestrator(
    *,
    available_agents: Sequence[AgentSpec | Agent | AugmentedLLM],
    planner: AgentSpec | Agent | AugmentedLLM | None = None,
    synthesizer: AgentSpec | Agent | AugmentedLLM | None = None,
    plan_type: Literal["full", "iterative"] = "full",
    provider: SupportedLLMProviders = "openai",
    model: str | ModelPreferences | None = None,
    overrides: OrchestratorOverrides | None = None,
    name: str | None = None,
    context: Context | None = None,
    **kwargs,
) -> Orchestrator:
    """
    In the orchestrator-workers workflow, a planner LLM dynamically breaks down tasks,
    delegates them to worker LLMs, and synthesizes their results. It does this
    in a loop until the task is complete.

    This is a simpler (and faster) form of the [deep orchestrator](https://github.com/lastmile-ai/mcp-agent/blob/main/src/mcp_agent/workflows/deep_orchestrator/README.md) workflow,
    which is more suitable for complex, long-running tasks with multiple agents and MCP servers where the number of agents is not known in advance.

    Args:
        available_agents: The agents/LLMs/workflows that can be used to execute the task.
        plan_type: The type of plan to use for the orchestrator ["full", "iterative"].
            "full" planning generates the full plan first, then executes. "iterative" plans the next step, and loops until success.
        provider: The provider to use for the LLM.
        model: The model to use as the LLM.
        overrides: Optional overrides for instructions and prompt templates.
        name: The name of this orchestrator workflow. Can be used as an identifier.
        context: The context to use for the orchestrator.
    """
    factory = _llm_factory(provider=provider, model=model, context=context)

    agents: List[Agent | AugmentedLLM] = []
    for item in available_agents:
        if isinstance(item, AgentSpec):
            agents.append(agent_from_spec(item, context=context))
        else:
            agents.append(item)

    planner_obj: Agent | AugmentedLLM | None = None
    synthesizer_obj: Agent | AugmentedLLM | None = None
    if planner:
        planner_obj = (
            planner
            if isinstance(planner, Agent | AugmentedLLM)
            else agent_from_spec(planner, context=context)
        )
    if synthesizer:
        synthesizer_obj = (
            synthesizer
            if isinstance(synthesizer, Agent | AugmentedLLM)
            else agent_from_spec(synthesizer, context=context)
        )

    return Orchestrator(
        llm_factory=factory,
        name=name,
        planner=planner_obj,
        synthesizer=synthesizer_obj,
        available_agents=agents,
        plan_type=plan_type,
        overrides=overrides,
        context=context,
        **kwargs,
    )


def create_deep_orchestrator(
    *,
    available_agents: Sequence[AgentSpec | Agent | AugmentedLLM],
    config: DeepOrchestratorConfig | None = None,
    name: str | None = None,
    provider: SupportedLLMProviders = "openai",
    model: str | ModelPreferences | None = None,
    context: Context | None = None,
    **kwargs,
) -> DeepOrchestrator:
    """
    Create a deep research-style orchestrator workflow that can be used to execute complex, long-running tasks with
    multiple agents and MCP servers.

    Args:
        available_agents: The agents/LLMs/workflows that can be used to execute the task.
        config: The configuration for the deep orchestrator.
        name: The name of this deep orchestrator workflow. Can be used as an identifier.
        provider: The provider to use for the LLM.
        model: The model to use as the LLM.
        context: The context to use for the LLM.
    """
    factory = _llm_factory(provider=provider, model=model, context=context)

    agents: List[Agent | AugmentedLLM] = (
        config.available_agents if config and config.available_agents else []
    )
    for item in available_agents:
        if isinstance(item, AgentSpec):
            agents.append(agent_from_spec(item, context=context))
        else:
            agents.append(item)

    if config is None:
        config = DeepOrchestratorConfig.from_simple()

    config.available_agents = agents
    config.name = name or config.name

    return DeepOrchestrator(
        llm_factory=factory,
        config=config,
        context=context,
        **kwargs,
    )


def create_parallel_llm(
    *,
    fan_in: AgentSpec | Agent | AugmentedLLM | Callable[[FanInInput], Any],
    fan_out: List[AgentSpec | Agent | AugmentedLLM | Callable] | None = None,
    name: str | None = None,
    provider: SupportedLLMProviders | None = "openai",
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context=None,
    **kwargs,
) -> ParallelLLM:
    """
    Create a parallel workflow that can fan out to multiple agents to execute in parallel, and fan in/aggregate the results.

    Args:
        fan_in: The agent/LLM/workflow that generates responses.
        fan_out: The agents/LLMs/workflows that generate responses.
        name: The name of the parallel workflow. Can be used to identify the workflow in logs.
        provider: The provider to use for the LLM.
        model: The model to use as the LLM.
        request_params: The default request parameters to use for the LLM.
        context: The context to use for the LLM.
    """
    factory = _llm_factory(
        provider=provider, model=model, request_params=request_params, context=context
    )

    fan_in_agent_or_llm: Agent | AugmentedLLM | Callable[[FanInInput], Any]
    if isinstance(fan_in, AgentSpec):
        fan_in_agent_or_llm = agent_from_spec(fan_in, context=context)
    else:
        fan_in_agent_or_llm = fan_in  # already Agent or AugmentedLLM or callable

    fan_out_agents: List[Agent | AugmentedLLM] = []
    fan_out_functions: List[Callable] = []
    for item in fan_out or []:
        if isinstance(item, AgentSpec):
            fan_out_agents.append(agent_from_spec(item, context=context))
        elif isinstance(item, Agent):
            fan_out_agents.append(item)
        elif isinstance(item, AugmentedLLM):
            fan_out_agents.append(item)
        elif callable(item):
            fan_out_functions.append(item)  # function

    return ParallelLLM(
        fan_in_agent=fan_in_agent_or_llm,
        fan_out_agents=fan_out_agents or None,
        fan_out_functions=fan_out_functions or None,
        name=name,
        llm_factory=factory,
        context=context,
        **kwargs,
    )


def create_evaluator_optimizer_llm(
    *,
    optimizer: AgentSpec | Agent | AugmentedLLM,
    evaluator: str | AgentSpec | Agent | AugmentedLLM,
    name: str | None = None,
    min_rating: int | None = None,
    max_refinements: int = 3,
    provider: SupportedLLMProviders | None = None,
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
    **kwargs,
) -> EvaluatorOptimizerLLM:
    """
    Create an evaluator-optimizer workflow that generates responses and evaluates them iteratively until they achieve a necessary quality criteria.

    Args:
        optimizer: The agent/LLM/workflow that generates responses.
        evaluator: The agent/LLM that evaluates responses
        name: The name of the evaluator-optimizer workflow.
        min_rating: Minimum acceptable quality rating
        max_refinements: Maximum refinement iterations (max number of times to refine the response)
        provider: The provider to use for the LLM.
        model: The model to use as the LLM.
        request_params: The default request parameters to use for the LLM.
        context: The context to use for the LLM.

    """
    factory = _llm_factory(
        provider=provider, model=model, request_params=request_params, context=context
    )
    optimizer_obj: AugmentedLLM | Agent
    evaluator_obj: str | AugmentedLLM | Agent

    optimizer_obj = (
        agent_from_spec(optimizer, context=context)
        if isinstance(optimizer, AgentSpec)
        else optimizer
    )
    if isinstance(evaluator, AgentSpec):
        evaluator_obj = agent_from_spec(evaluator, context=context)
    else:
        evaluator_obj = evaluator

    return EvaluatorOptimizerLLM(
        optimizer=optimizer_obj,
        evaluator=evaluator_obj,
        name=name,
        min_rating=min_rating,
        max_refinements=max_refinements,
        llm_factory=factory,
        context=context,
        **kwargs,
    )


def create_swarm(
    *,
    name: str,
    instruction: str | Callable[[dict], str] | None = None,
    server_names: List[str] | None = None,
    functions: List[Callable] | None = None,
    provider: Literal["openai", "anthropic"] = "openai",
    context: Context | None = None,
) -> Swarm:
    """
    Create a swarm agent that can use tools via MCP servers.
    Swarm agents can use tools to handoff to other agents, and communnicate with MCP servers.

    Args:
        name: str - The name of the swarm agent.
        instruction: str | Callable[[dict], str] | None - The instruction for the swarm agent.
        server_names: List[str] | None - The server names to use for the swarm agent.
        functions: List[Callable] | None - The functions to use for the swarm agent.
        provider: Literal["openai", "anthropic"] - The provider to use for the swarm agent.
        context: Context | None - The context to use for the swarm agent.
    """

    swarm_agent = SwarmAgent(
        name=name,
        instruction=instruction or "You are a helpful agent.",
        server_names=server_names,
        functions=functions,
        context=context,
    )
    if provider.lower() == "openai":
        from mcp_agent.workflows.swarm.swarm_openai import OpenAISwarm

        return OpenAISwarm(agent=swarm_agent)
    if provider.lower() == "anthropic":
        from mcp_agent.workflows.swarm.swarm_anthropic import AnthropicSwarm

        return AnthropicSwarm(agent=swarm_agent)
    raise ValueError(
        f"Unsupported swarm provider: {provider}. Currently supported providers are: ['openai', 'anthropic']. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
    )


async def create_intent_classifier_llm(
    *,
    intents: List[Intent],
    provider: Literal["openai", "anthropic"] = "openai",
    model: str | ModelPreferences | None = None,
    classification_instruction: str | None = None,
    name: str | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
) -> LLMIntentClassifier:
    """
    Create an intent classifier that uses an LLM to classify the given intents.

    Args:
        intents: List[Intent] - The list of intents to classify.
        provider: Literal["openai", "anthropic"] - The LLM provider to use.
        model: str | ModelPreferences | None - The model to use as the LLM.
        classification_instruction: str | None - The instruction to the LLM.
        name: str | None - The name of the intent classifier.
        request_params: RequestParams | None - The default request parameters to use for the LLM.
        context: Context | None - Context object for the intent classifier.
    """

    prov = provider.lower()
    request_params = _merge_model_preferences(
        provider=provider, model=model, request_params=request_params, context=context
    )

    if prov == "openai":
        from mcp_agent.workflows.intent_classifier.intent_classifier_llm_openai import (
            OpenAILLMIntentClassifier,
        )

        llm_cls = _get_provider_class(prov)
        return await OpenAILLMIntentClassifier.create(
            llm=llm_cls(
                name=name,
                instruction=classification_instruction,
                default_request_params=request_params,
                context=context,
            ),
            intents=intents,
            classification_instruction=classification_instruction,
            name=name,
            context=context,
        )
    if prov == "anthropic":
        from mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic import (
            AnthropicLLMIntentClassifier,
        )

        llm_cls = _get_provider_class(prov)
        return await AnthropicLLMIntentClassifier.create(
            llm=llm_cls(
                name=name,
                instruction=classification_instruction,
                default_request_params=request_params,
                context=context,
            ),
            intents=intents,
            classification_instruction=classification_instruction,
            name=name,
            context=context,
        )
    raise ValueError(
        f"Unsupported intent classifier provider: {provider}. Currently supported providers are: ['openai', 'anthropic']. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
    )


async def create_intent_classifier_embedding(
    *,
    intents: List[Intent],
    provider: SupportedEmbeddingProviders = "openai",
    model: EmbeddingModel | None = None,
    context: Context | None = None,
) -> EmbeddingIntentClassifier:
    """
    Create an intent classifier that uses embedding similarity to classify intents.

    Args:
        intents: List[Intent] - The list of intents to classify.
        provider: Literal["openai", "cohere"] - The provider to use for embedding generation.
        context: Context | None - Context object for the intent classifier.
    """

    if provider.lower() == "openai":
        from mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai import (
            OpenAIEmbeddingIntentClassifier,
        )

        return await OpenAIEmbeddingIntentClassifier.create(
            intents=intents, embedding_model=model, context=context
        )
    if provider.lower() == "cohere":
        from mcp_agent.workflows.intent_classifier.intent_classifier_embedding_cohere import (
            CohereEmbeddingIntentClassifier,
        )

        return await CohereEmbeddingIntentClassifier.create(
            intents=intents, embedding_model=model, context=context
        )
    raise ValueError(
        f"Unsupported embedding provider: {provider}. Currently supported providers are: ['openai', 'cohere']. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
    )


# region AgentSpec loaders


def _resolve_callable(ref: str) -> Callable:
    """Resolve a dotted reference 'package.module:attr' to a callable.
    Raises ValueError if not found or not callable.
    """
    if not isinstance(ref, str) or (":" not in ref and "." not in ref):
        raise ValueError(f"Invalid callable reference: {ref}")
    module_name, attr = ref.split(":", 1) if ":" in ref else ref.rsplit(".", 1)
    mod = importlib.import_module(module_name)
    obj = getattr(mod, attr)
    if not callable(obj):
        raise ValueError(f"Referenced object is not callable: {ref}")
    return obj


def _normalize_agents_data(data: Any) -> list[dict]:
    """Normalize arbitrary parsed data into a list of agent dicts.

    Accepts:
      - {'agents': [...]} or {'agent': {...}} or a list of agents or a single agent dict
    """
    if data is None:
        return []
    if isinstance(data, dict):
        if "agents" in data and isinstance(data["agents"], list):
            return data["agents"]
        if "agent" in data and isinstance(data["agent"], dict):
            return [data["agent"]]
        # If the dict looks like a single agent (has a name), treat it as one
        if "name" in data:
            return [data]
        return []
    if isinstance(data, list):
        return data
    return []


def _agent_spec_from_dict(
    obj: dict, context: Context | None = None, *, default_instruction: str | None = None
) -> AgentSpec:
    name = obj.get("name")
    if not name:
        raise ValueError("AgentSpec requires a 'name'")
    instruction = obj.get("instruction")
    # If no explicit instruction, fall back to 'description' or provided default body text
    if not instruction:
        desc = obj.get("description")
        if default_instruction and desc:
            instruction = f"{desc}\n\n{default_instruction}".strip()
        else:
            instruction = default_instruction or desc
    server_names = obj.get("server_names") or obj.get("servers") or []
    # TODO: saqadri - Claude subagents usually specify 'tools' that are not MCP server names.
    # For now, we map 'tools' to server_names as a convenience, but this should be modeled separately.
    connection_persistence = obj.get("connection_persistence", True)
    functions = obj.get("functions", [])
    # If no servers provided, consider 'tools' as a hint for server names
    if not server_names and "tools" in obj:
        tools_val = obj.get("tools")
        if isinstance(tools_val, str):
            server_names = [t.strip() for t in tools_val.split(",") if t.strip()]
        elif isinstance(tools_val, list):
            server_names = [str(t).strip() for t in tools_val if str(t).strip()]
    resolved_functions: list[Callable] = []
    for f in functions:
        if callable(f):
            resolved_functions.append(f)
        elif isinstance(f, str):
            resolved_functions.append(_resolve_callable(f))
        else:
            raise ValueError(f"Unsupported function entry: {f}")
    human_cb = obj.get("human_input_callback")
    if isinstance(human_cb, str):
        human_cb = _resolve_callable(human_cb)

    return AgentSpec(
        name=name,
        instruction=instruction,
        server_names=list(server_names),
        functions=resolved_functions,
        connection_persistence=connection_persistence,
        human_input_callback=human_cb,
    )


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise ImportError("PyYAML is required to load YAML agent specs") from e
    return yaml.safe_load(text)


def _extract_front_matter_md(text: str) -> str | None:
    """Extract YAML front-matter delimited by --- at the top of a Markdown file.

    Allows leading whitespace/BOM before the first ---.
    """
    s = text.lstrip("\ufeff\r\n \t")
    if s.startswith("---\n"):
        end = s.find("\n---", 4)
        if end != -1:
            return s[4:end]
    return None


def _extract_front_matter_and_body_md(text: str) -> tuple[str | None, str]:
    """Return (front_matter_yaml, body_text).

    Allows leading whitespace/BOM before front matter.
    """
    s = text.lstrip("\ufeff\r\n \t")
    if s.startswith("---\n"):
        end = s.find("\n---", 4)
        if end != -1:
            fm = s[4:end]
            body = s[end + len("\n---") :].lstrip("\n")
            return fm, body
    return None, text


def _extract_code_blocks_md(text: str) -> list[tuple[str, str]]:
    """Return list of (lang, code) for fenced code blocks.

    Relaxed to allow attributes after language, e.g. ```yaml title="...".
    """
    pattern = re.compile(
        r"```\s*([A-Za-z0-9_-]+)(?:[^\n]*)?\n([\s\S]*?)```", re.MULTILINE
    )
    return [(m.group(1) or "", m.group(2)) for m in pattern.finditer(text)]


def load_agent_specs_from_text(
    text: str, *, fmt: str | None = None, context: Context | None = None
) -> List[AgentSpec]:
    """Load AgentSpec list from text in yaml/json/md.

    - YAML: either a list or {'agents': [...]}
    - JSON: same as YAML
    - Markdown: supports YAML front-matter or fenced code blocks with yaml/json containing agents
    """
    specs: list[AgentSpec] = []
    fmt_lower = (fmt or "").lower()
    try_parsers = []
    if fmt_lower in ("yaml", "yml"):
        try_parsers = [lambda t: _load_yaml(t)]
    elif fmt_lower == "json":
        try_parsers = [lambda t: json.loads(t)]
    elif fmt_lower == "md":
        fm, body = _extract_front_matter_and_body_md(text)
        if fm is not None:
            try_parsers.append(lambda _t, fm=fm: ("__FM__", _load_yaml(fm), body))
        for lang, code in _extract_code_blocks_md(text):
            lang = (lang or "").lower()
            if lang in ("yaml", "yml"):
                try_parsers.append(
                    lambda _t, code=code: ("__YAML__", _load_yaml(code), "")
                )
            elif lang == "json":
                try_parsers.append(
                    lambda _t, code=code: ("__JSON__", json.loads(code), "")
                )
    else:
        # Try yaml then json by default
        try_parsers = [lambda t: _load_yaml(t), lambda t: json.loads(t)]

    for parser in try_parsers:
        try:
            data = parser(text)
        except Exception:
            continue
        body_text: str | None = None
        if (
            isinstance(data, tuple)
            and len(data) == 3
            and isinstance(data[1], (dict, list))
        ):
            # Markdown parser variant returned (tag, parsed, body)
            _, parsed, body_text = data
            data = parsed

        agents_data = _normalize_agents_data(data)
        for obj in agents_data:
            try:
                specs.append(
                    _agent_spec_from_dict(
                        obj, context=context, default_instruction=body_text
                    )
                )
            except Exception:
                continue
        if specs:
            break
    return specs


def load_agent_specs_from_file(path: str, context=None) -> List[AgentSpec]:
    ext = os.path.splitext(path)[1].lower()
    fmt = None
    if ext in (".yaml", ".yml"):
        fmt = "yaml"
    elif ext == ".json":
        fmt = "json"
    elif ext in (".md", ".markdown"):
        fmt = "md"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return load_agent_specs_from_text(text, fmt=fmt, context=context)


def load_agent_specs_from_dir(
    path: str, pattern: str = "**/*.*", context=None
) -> List[AgentSpec]:
    """Load AgentSpec list by scanning a directory for yaml/json/md files."""
    results: List[AgentSpec] = []
    for fp in glob(os.path.join(path, pattern), recursive=True):
        if os.path.isdir(fp):
            continue
        ext = os.path.splitext(fp)[1].lower()
        if ext not in (".yaml", ".yml", ".json", ".md", ".markdown"):
            continue
        try:
            results.extend(load_agent_specs_from_file(fp, context=context))
        except Exception:
            continue
    return results


# endregion


# region helpers


def _parse_model_identifier(model_id: str) -> Tuple[str | None, str]:
    """Parse a model identifier that may be prefixed with provider (e.g., 'openai:gpt-4o')."""
    if ":" in model_id:
        prov, name = model_id.split(":", 1)
        return (prov.strip().lower() or None, name.strip())
    return (None, model_id)


def _select_provider_and_model(
    *,
    model: str | ModelPreferences | None = None,
    provider: SupportedLLMProviders | None = None,
    context: Context | None = None,
) -> Tuple[str, str | None]:
    """
    Return (provider, model_name) using a string model id or ModelSelector.

    - If model is a str, treat it as model id; allow 'provider:model' pattern.
    - If it's a ModelPreferences, use ModelSelector.
    - Otherwise, return default provider and no model.
    """
    prov = (provider or "openai").lower()
    if isinstance(model, str):
        inferred_provider, model_name = _parse_model_identifier(model)
        return (inferred_provider or prov, model_name)
    if isinstance(model, ModelPreferences):
        selector = ModelSelector(context=context)
        model_info = selector.select_best_model(model_preferences=model, provider=prov)
        return (model_info.provider.lower(), model_info.name)
    return (prov, None)


def _merge_model_preferences(
    provider: str | None = None,
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
) -> RequestParams:
    """
    Merge model preferences from provider, model, and request params.
    Explicitly specified model takes precedence over request_params.
    """

    _, model_name = _select_provider_and_model(
        provider=provider,
        model=model or getattr(request_params, "model", None),
        context=context,
    )

    if request_params is not None:
        if model_name and isinstance(model, ModelPreferences):
            request_params.model = model_name
            request_params.modelPreferences = model
        elif model_name and isinstance(model, str):
            request_params.model = model_name
        elif isinstance(model, ModelPreferences):
            request_params.modelPreferences = model
    else:
        request_params = RequestParams(model=model_name)
        if isinstance(model, ModelPreferences):
            request_params.modelPreferences = model

    return request_params


def _get_provider_class(
    provider: SupportedLLMProviders,
):
    p = provider.lower()
    if p == "openai":
        from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

        return OpenAIAugmentedLLM
    if p == "anthropic":
        from mcp_agent.workflows.llm.augmented_llm_anthropic import (
            AnthropicAugmentedLLM,
        )

        return AnthropicAugmentedLLM
    if p == "azure":
        from mcp_agent.workflows.llm.augmented_llm_azure import AzureAugmentedLLM

        return AzureAugmentedLLM
    if p == "google":
        from mcp_agent.workflows.llm.augmented_llm_google import GoogleAugmentedLLM

        return GoogleAugmentedLLM
    if p == "bedrock":
        from mcp_agent.workflows.llm.augmented_llm_bedrock import BedrockAugmentedLLM

        return BedrockAugmentedLLM
    if p == "ollama":
        from mcp_agent.workflows.llm.augmented_llm_ollama import OllamaAugmentedLLM

        return OllamaAugmentedLLM

    raise ValueError(
        f"mcp-agent doesn't support provider: {provider}. To request support, please create an issue at https://github.com/lastmile-ai/mcp-agent/issues"
    )


def _llm_factory(
    *,
    provider: SupportedLLMProviders | None = None,
    model: str | ModelPreferences | None = None,
    request_params: RequestParams | None = None,
    context: Context | None = None,
) -> Callable[[Agent], AugmentedLLM]:
    prov, model_name = _select_provider_and_model(
        provider=provider,
        model=model or getattr(request_params, "model", None),
        context=context,
    )
    provider_cls = _get_provider_class(prov)

    def _default_params() -> RequestParams | None:
        if model_name and isinstance(model, ModelPreferences):
            return RequestParams(model=model_name, modelPreferences=model)
        if model_name and isinstance(model, str):
            return RequestParams(model=model_name)
        if isinstance(model, ModelPreferences):
            return RequestParams(modelPreferences=model)
        return None

    return lambda agent: provider_cls(
        agent=agent,
        default_request_params=request_params or _default_params(),
        context=context,
    )


# endregion
