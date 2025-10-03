from typing import Callable, List, Optional, TYPE_CHECKING

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.embedding.embedding_openai import OpenAIEmbeddingModel
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.workflows.router.router_embedding import EmbeddingRouter

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class OpenAIEmbeddingRouter(EmbeddingRouter):
    """
    A router that uses OpenAI embedding similarity to route requests to appropriate categories.
    This class helps to route an input to a specific MCP server, an Agent (an aggregation of MCP servers),
    or a function (any Callable).
    """

    def __init__(
        self,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        embedding_model: OpenAIEmbeddingModel | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        embedding_model = embedding_model or OpenAIEmbeddingModel()

        super().__init__(
            embedding_model=embedding_model,
            server_names=server_names,
            agents=agents,
            functions=functions,
            context=context,
            **kwargs,
        )

    @classmethod
    async def create(
        cls,
        embedding_model: OpenAIEmbeddingModel | None = None,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        context: Optional["Context"] = None,
    ) -> "OpenAIEmbeddingRouter":
        """
        Factory method to create and initialize a router.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            server_names=server_names,
            agents=agents,
            functions=functions,
            embedding_model=embedding_model,
            context=context,
        )
        await instance.initialize()
        return instance
