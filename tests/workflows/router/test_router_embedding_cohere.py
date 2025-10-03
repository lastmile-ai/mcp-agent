import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
from typing import List

from mcp_agent.workflows.router.router_embedding import EmbeddingRouter
from mcp_agent.workflows.router.router_embedding_cohere import CohereEmbeddingRouter


class MockCohereEmbeddingModel:
    """Mock CohereEmbeddingModel for testing."""

    def __init__(self, model="embed-english-v3.0", context=None, **kwargs):
        self.model = model
        self.context = context
        self.embedding_dim = 1024  # Cohere's typical embedding dimension
        self.kwargs = kwargs

    async def embed(self, data: List[str]) -> np.ndarray:
        """Mock embed method that returns random embeddings."""
        embedding_dim = 1024
        embeddings = np.ones((len(data), embedding_dim), dtype=np.float32)
        for i in range(len(data)):
            # Simple hashing to create different embeddings for different strings
            seed = sum(ord(c) for c in data[i])
            np.random.seed(seed)
            embeddings[i] = np.random.rand(embedding_dim).astype(np.float32)
        return embeddings


class TestCohereEmbeddingRouter:
    """Tests for the CohereEmbeddingRouter class."""

    @pytest.fixture
    def setup_cohere_context(self, mock_context):
        """Add Cohere-specific configuration to the mock context."""
        mock_context.config.cohere = MagicMock()
        mock_context.config.cohere.api_key = "test_api_key"
        return mock_context

    # Test 1: Basic initialization
    def test_initialization(self, setup_cohere_context, mock_agent, test_function):
        """Tests basic initialization of the router."""
        # Initialize router with default embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = CohereEmbeddingRouter(
                server_names=["test_server"],
                agents=[mock_agent],
                functions=[test_function],
                context=setup_cohere_context,
            )

            # Assertions
            assert router is not None
            assert isinstance(router, EmbeddingRouter)
            assert isinstance(router.embedding_model, MockCohereEmbeddingModel)
            assert router.embedding_model.model == "embed-english-v3.0"  # Default model
            assert router.server_names == ["test_server"]
            assert router.agents == [mock_agent]
            assert router.functions == [test_function]
            assert router.context == setup_cohere_context
            assert router.initialized is False

    # Test 2: Initialization with custom embedding model
    def test_initialization_with_custom_embedding_model(
        self, setup_cohere_context, mock_agent
    ):
        """Tests initialization with a custom embedding model."""
        # Create custom embedding model
        custom_model = MockCohereEmbeddingModel(model="embed-multilingual-v3.0")

        # Initialize router with custom embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = CohereEmbeddingRouter(
                server_names=["test_server"],
                agents=[mock_agent],
                embedding_model=custom_model,
                context=setup_cohere_context,
            )

            # Assertions
            assert router is not None
            assert router.embedding_model == custom_model
            assert router.embedding_model.model == "embed-multilingual-v3.0"

    # Test 3: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(self, setup_cohere_context, mock_agent):
        """Tests the factory method for creating and initializing a router."""
        # Create router using factory method with mock embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = await CohereEmbeddingRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_cohere_context,
            )

            # Assertions
            assert router is not None
            assert router.initialized is True
            assert isinstance(router.embedding_model, MockCohereEmbeddingModel)
            assert router.server_names == ["test_server"]
            assert router.agents == [mock_agent]
            assert router.context == setup_cohere_context
            assert len(router.server_categories) == 1
            assert len(router.agent_categories) == 1

            # Categories should have embeddings
            server_category = router.server_categories["test_server"]
            assert server_category.embedding is not None
            assert isinstance(server_category.embedding, np.ndarray)

    # Test 4: Factory method with custom embedding model
    @pytest.mark.asyncio
    async def test_create_with_custom_embedding_model(
        self, setup_cohere_context, mock_agent
    ):
        """Tests the factory method with a custom embedding model."""
        # Create custom embedding model
        custom_model = MockCohereEmbeddingModel(model="embed-multilingual-v3.0")

        # Create router using factory method with custom embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = await CohereEmbeddingRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                embedding_model=custom_model,
                context=setup_cohere_context,
            )

            # Assertions
            assert router is not None
            assert router.initialized is True
            assert router.embedding_model == custom_model
            assert router.embedding_model.model == "embed-multilingual-v3.0"

    # Test 5: Default embedding model creation
    def test_default_embedding_model_creation(self, setup_cohere_context):
        """Tests that the default embedding model is created correctly when not provided."""
        # Initialize router without providing an embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel"
        ) as mock_model_class:
            mock_model_class.return_value = MagicMock()

            router = CohereEmbeddingRouter(
                server_names=["test_server"],
                context=setup_cohere_context,
            )

            # Assertions
            mock_model_class.assert_called_once()
            assert router.embedding_model is not None

    # Test 6: Routing functionality (integration with EmbeddingRouter)
    @pytest.mark.asyncio
    async def test_routing_functionality(self, setup_cohere_context, mock_agent):
        """Tests that the routing functionality works correctly."""
        # Initialize router with mock embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = await CohereEmbeddingRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_cohere_context,
            )

            # Create a spy on _route_with_embedding method
            original_route_with_embedding = router._route_with_embedding
            router._route_with_embedding = AsyncMock(
                wraps=original_route_with_embedding
            )

            # Test routing
            await router.route("Test request")

            # Assertions
            assert router._route_with_embedding.called
            call_args = router._route_with_embedding.call_args
            assert call_args[0][0] == "Test request"

    # Test 7: Full routing flow
    @pytest.mark.asyncio
    async def test_full_routing_flow(self, setup_cohere_context, mock_agent):
        """Tests the full routing flow from request to embedding to result."""
        # Initialize router with mock embedding model
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = await CohereEmbeddingRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_cohere_context,
            )

            # Mock the embed method to track calls
            original_embed = router.embedding_model.embed
            router.embedding_model.embed = AsyncMock(side_effect=original_embed)

            # Test routing
            results = await router.route("Test request")

            # Assertions
            assert router.embedding_model.embed.called
            assert len(results) > 0  # Should have at least one result

            # Results should include either server or agent
            result_values = [r.result for r in results]
            assert any(
                val == "test_server" or val == mock_agent for val in result_values
            )

    # Test 8: Integration with parent EmbeddingRouter methods
    @pytest.mark.asyncio
    async def test_integration_with_parent_methods(
        self, setup_cohere_context, mock_agent
    ):
        """Tests that CohereEmbeddingRouter properly integrates with parent EmbeddingRouter methods."""
        # Initialize router
        with patch(
            "mcp_agent.workflows.router.router_embedding_cohere.CohereEmbeddingModel",
            MockCohereEmbeddingModel,
        ):
            router = await CohereEmbeddingRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_cohere_context,
            )

            # Test route_to_server method
            await router.route_to_server("Server request")

            # Test route_to_agent method
            await router.route_to_agent("Agent request")

            # Assertions - mainly checking that these methods run without errors
            assert router.initialized is True
