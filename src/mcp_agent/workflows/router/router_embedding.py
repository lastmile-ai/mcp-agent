from typing import Callable, List, Optional, TYPE_CHECKING

from numpy import mean

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.embedding.embedding_base import (
    EmbeddingModel,
    FloatArray,
    compute_similarity_scores,
    compute_confidence,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.workflows.router.router_base import (
    Router,
    RouterCategory,
    RouterResult,
)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class EmbeddingRouterCategory(RouterCategory):
    """A category for embedding-based routing"""

    embedding: FloatArray | None = None
    """Pre-computed embedding for this category"""


class EmbeddingRouter(Router):
    """
    A router that uses embedding similarity to route requests to appropriate categories.
    This class helps to route an input to a specific MCP server, an Agent (an aggregation of MCP servers),
    or a function (any Callable).

    Features:
    - Semantic similarity based routing using embeddings
    - Flexible embedding model support
    - Support for formatting and combining category metadata

    Example usage:
        # Initialize router with embedding model
        router = EmbeddingRouter(
            embedding_model=OpenAIEmbeddingModel(model="text-embedding-3-small"),
            mcp_servers_names=["customer_service", "tech_support"],
        )

        # Route a request
        results = await router.route("My laptop keeps crashing")
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(
            server_names=server_names,
            agents=agents,
            functions=functions,
            context=context,
            **kwargs,
        )

        self.embedding_model = embedding_model

    @classmethod
    async def create(
        cls,
        embedding_model: EmbeddingModel,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        context: Optional["Context"] = None,
    ) -> "EmbeddingRouter":
        """
        Factory method to create and initialize a router.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            embedding_model=embedding_model,
            server_names=server_names,
            agents=agents,
            functions=functions,
            context=context,
        )
        await instance.initialize()
        return instance

    async def initialize(self):
        """Initialize by computing embeddings for all categories"""

        async def create_category_with_embedding(
            category: RouterCategory,
        ) -> EmbeddingRouterCategory:
            # Get formatted text representation of category
            category_text = self.format_category(category)
            embedding = await self._compute_embedding([category_text])
            category_with_embedding = EmbeddingRouterCategory(
                **category.model_dump(), embedding=embedding
            )

            return category_with_embedding

        if self.initialized:
            return

        # Create categories for servers, agents, and functions
        await super().initialize()
        self.initialized = False  # We are not initialized yet

        for name, category in self.server_categories.items():
            category_with_embedding = await create_category_with_embedding(category)
            self.server_categories[name] = category_with_embedding
            self.categories[name] = category_with_embedding

        for name, category in self.agent_categories.items():
            category_with_embedding = await create_category_with_embedding(category)
            self.agent_categories[name] = category_with_embedding
            self.categories[name] = category_with_embedding

        for name, category in self.function_categories.items():
            category_with_embedding = await create_category_with_embedding(category)
            self.function_categories[name] = category_with_embedding
            self.categories[name] = category_with_embedding

        self.initialized = True

    async def route(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[str | Agent | AugmentedLLM | Callable]]:
        """Route the request based on embedding similarity"""
        if not self.initialized:
            await self.initialize()

        return await self._route_with_embedding(request, top_k)

    async def route_to_server(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[str]]:
        """Route specifically to server categories"""
        if not self.initialized:
            await self.initialize()

        results = await self._route_with_embedding(
            request,
            top_k,
            include_servers=True,
            include_agents=False,
            include_functions=False,
        )
        return [r.result for r in results[:top_k]]

    async def route_to_agent(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[Agent | AugmentedLLM]]:
        """Route specifically to agent categories"""
        if not self.initialized:
            await self.initialize()

        results = await self._route_with_embedding(
            request,
            top_k,
            include_servers=False,
            include_agents=True,
            include_functions=False,
        )
        return [r.result for r in results[:top_k]]

    async def route_to_function(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[Callable]]:
        """Route specifically to function categories"""
        if not self.initialized:
            await self.initialize()

        results = await self._route_with_embedding(
            request,
            top_k,
            include_servers=False,
            include_agents=False,
            include_functions=True,
        )
        return [r.result for r in results[:top_k]]

    async def _route_with_embedding(
        self,
        request: str,
        top_k: int = 1,
        include_servers: bool = True,
        include_agents: bool = True,
        include_functions: bool = True,
    ) -> List[RouterResult]:
        def create_result(category: RouterCategory, request_embedding):
            if category.embedding is None:
                return None

            similarity = compute_similarity_scores(
                request_embedding, category.embedding
            )

            return RouterResult(
                p_score=compute_confidence(similarity), result=category.category
            )

        request_embedding = await self._compute_embedding([request])

        results: List[RouterResult] = []
        if include_servers:
            for _, category in self.server_categories.items():
                result = create_result(category, request_embedding)
                if result:
                    results.append(result)

        if include_agents:
            for _, category in self.agent_categories.items():
                result = create_result(category, request_embedding)
                if result:
                    results.append(result)

        if include_functions:
            for _, category in self.function_categories.items():
                result = create_result(category, request_embedding)
                if result:
                    results.append(result)

        results.sort(key=lambda x: x.p_score, reverse=True)
        return results[:top_k]

    async def _compute_embedding(self, data: List[str]):
        # Get embedding for the provided text
        embeddings = await self.embedding_model.embed(data)

        # Use mean pooling to combine embeddings
        embedding = mean(embeddings, axis=0)

        return embedding
