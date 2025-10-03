from typing import Callable, List, Optional, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.router.router_llm import LLMRouter

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class AnthropicLLMRouter(LLMRouter):
    """
    An LLM router that uses an Anthropic model to make routing decisions.
    """

    def __init__(
        self,
        name: str | None = None,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        routing_instruction: str | None = None,
        request_params: RequestParams | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            llm_factory=lambda agent, **kw: AnthropicAugmentedLLM(
                agent=agent,
                instruction=kw.get("instruction"),
                default_request_params=request_params,
                context=context,
            ),
            server_names=server_names,
            agents=agents,
            functions=functions,
            routing_instruction=routing_instruction,
            context=context,
            **kwargs,
        )

    @classmethod
    async def create(
        cls,
        name: str | None = None,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        routing_instruction: str | None = None,
        request_params: RequestParams | None = None,
        context: Optional["Context"] = None,
    ) -> "AnthropicLLMRouter":
        """
        Factory method to create and initialize a router.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            name=name,
            server_names=server_names,
            agents=agents,
            functions=functions,
            routing_instruction=routing_instruction,
            request_params=request_params,
            context=context,
        )
        await instance.initialize()
        return instance
