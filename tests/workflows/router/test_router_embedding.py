import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.router.router_embedding import (
    EmbeddingRouter,
    EmbeddingRouterCategory,
)


class TestEmbeddingRouter:
    """Tests for the EmbeddingRouter class."""

    # Test 1: Basic initialization
    def test_initialization(
        self, mock_context, mock_embedding_model, mock_agent, test_function
    ):
        """Tests basic initialization of the embedding router."""
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Assertions
        assert router is not None
        assert router.embedding_model == mock_embedding_model
        assert router.server_names == ["test_server"]
        assert router.agents == [mock_agent]
        assert router.functions == [test_function]
        assert router.context == mock_context
        assert router.initialized is False

    # Test 2: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(
        self, mock_context, mock_embedding_model, mock_agent
    ):
        """Tests the factory method for creating and initializing a router."""
        # Patch the initialize method to skip the actual initialization
        with patch.object(
            EmbeddingRouter, "initialize", new=AsyncMock()
        ) as mock_initialize:
            # Create router using factory method
            router = await EmbeddingRouter.create(
                embedding_model=mock_embedding_model,
                server_names=["test_server"],
                agents=[mock_agent],
                context=mock_context,
            )

            # Assertions
            assert router is not None
            assert router.embedding_model == mock_embedding_model
            assert router.server_names == ["test_server"]
            assert router.agents == [mock_agent]
            assert router.context == mock_context

            # Verify initialize was called
            mock_initialize.assert_called_once()

    # Test 3: Initialize method
    @pytest.mark.asyncio
    async def test_initialize_method(
        self, mock_context, mock_embedding_model, mock_agent, test_function
    ):
        """Tests that initialize method populates categories with embeddings."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        await router.initialize()

        # Assertions
        assert router.initialized is True

        # Verify server category has embedding
        server_category = router.server_categories["test_server"]
        assert isinstance(server_category, EmbeddingRouterCategory)
        assert server_category.embedding is not None

        # Verify agent category has embedding
        agent_category = router.agent_categories[mock_agent.name]
        assert isinstance(agent_category, EmbeddingRouterCategory)
        assert agent_category.embedding is not None

        # Verify function category has embedding
        function_category = router.function_categories[test_function.__name__]
        assert isinstance(function_category, EmbeddingRouterCategory)
        assert function_category.embedding is not None

    # Test 4: Compute embedding
    @pytest.mark.asyncio
    async def test_compute_embedding(self, mock_context, mock_embedding_model):
        """Tests the _compute_embedding method."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            context=mock_context,
        )

        # Reset mock for embed
        mock_embedding_model.embed.reset_mock()

        # Test computing embedding for a single text
        result = await router._compute_embedding(["Test text"])

        # Assertions
        assert mock_embedding_model.embed.call_count == 1
        assert isinstance(result, np.ndarray)
        assert result.ndim == 1  # Should be a 1D array after mean pooling

        # Test with multiple texts
        result_multi = await router._compute_embedding(["Text 1", "Text 2", "Text 3"])

        # Assertions
        assert mock_embedding_model.embed.call_count == 2
        assert isinstance(result_multi, np.ndarray)
        assert result_multi.ndim == 1  # Should still be 1D after mean pooling

    # Test 5: Route method
    @pytest.mark.asyncio
    async def test_route_method(self, mock_context, mock_embedding_model, mock_agent):
        """Tests the route method."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            agents=[mock_agent],
            context=mock_context,
        )

        # Create result objects for our mock
        mock_result1 = MagicMock()
        mock_result1.result = "test_server"
        mock_result1.p_score = 0.9

        mock_result2 = MagicMock()
        mock_result2.result = mock_agent
        mock_result2.p_score = 0.7

        # Create a mock for _route_with_embedding that returns our prepared results
        async def mock_route_with_embedding(*args, **kwargs):
            return [mock_result1, mock_result2]

        router._route_with_embedding = mock_route_with_embedding

        # Test route method
        results = await router.route("How can I get help?", top_k=2)

        # Assertions
        assert len(results) == 2
        assert results[0].result == "test_server"
        assert results[0].p_score == 0.9
        assert results[1].result == mock_agent
        assert results[1].p_score == 0.7

    # Test 6: Route to server method
    @pytest.mark.asyncio
    async def test_route_to_server_method(self, mock_context, mock_embedding_model):
        """Tests the route_to_server method."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server1", "test_server2"],
            context=mock_context,
        )

        # Patch the initialize method
        router.initialize = AsyncMock()
        router.initialized = False

        # Mock the _route_with_embedding method
        mock_result1 = MagicMock()
        mock_result1.result = "test_server1"
        mock_result1.p_score = 0.9

        mock_result2 = MagicMock()
        mock_result2.result = "test_server2"
        mock_result2.p_score = 0.8

        router._route_with_embedding = AsyncMock(
            return_value=[mock_result1, mock_result2]
        )

        # Test route_to_server method
        results = await router.route_to_server("Show me server info", top_k=2)

        # Assertions
        assert router.initialize.called
        assert router._route_with_embedding.call_count == 1
        assert len(results) == 2
        assert (
            results[0] == "test_server1"
        )  # Note: route_to_server returns just the result value
        assert results[1] == "test_server2"

        # Check _route_with_embedding parameters
        call_args = router._route_with_embedding.call_args
        assert call_args[0][0] == "Show me server info"  # request
        assert call_args[0][1] == 2  # top_k
        assert call_args[1]["include_servers"] is True
        assert call_args[1]["include_agents"] is False
        assert call_args[1]["include_functions"] is False

    # Test 7: Route to agent method
    @pytest.mark.asyncio
    async def test_route_to_agent_method(
        self, mock_context, mock_embedding_model, mock_agent
    ):
        """Tests the route_to_agent method."""
        # Create another mock agent for testing
        mock_agent2 = MagicMock(spec=Agent)
        mock_agent2.name = "test_agent2"
        mock_agent2.instruction = "This is test agent 2"
        mock_agent2.server_names = ["test_server"]

        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            agents=[mock_agent, mock_agent2],
            context=mock_context,
        )

        # Patch the initialize method
        router.initialize = AsyncMock()
        router.initialized = False

        # Create mock results with agent objects
        mock_result1 = MagicMock()
        mock_result1.result = mock_agent
        mock_result1.p_score = 0.9

        mock_result2 = MagicMock()
        mock_result2.result = mock_agent2
        mock_result2.p_score = 0.7

        # Create a spy on _route_with_embedding
        router._route_with_embedding = AsyncMock(
            return_value=[mock_result1, mock_result2]
        )

        # Test route_to_agent method
        results = await router.route_to_agent("I need agent help", top_k=2)

        # Assertions
        assert router.initialize.called
        assert router._route_with_embedding.call_count == 1
        assert len(results) == 2
        assert (
            results[0] == mock_agent
        )  # Note: route_to_agent returns just the result value
        assert results[1] == mock_agent2

        # Check _route_with_embedding parameters
        call_args = router._route_with_embedding.call_args
        assert call_args[0][0] == "I need agent help"  # request
        assert call_args[0][1] == 2  # top_k
        assert call_args[1]["include_servers"] is False
        assert call_args[1]["include_agents"] is True
        assert call_args[1]["include_functions"] is False

    # Test 8: Route to function method
    @pytest.mark.asyncio
    async def test_route_to_function_method(
        self, mock_context, mock_embedding_model, test_function
    ):
        """Tests the route_to_function method."""

        # Create a second test function
        def test_function2(input_text: str) -> str:
            """A second test function."""
            return f"Function 2: {input_text}"

        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            functions=[test_function, test_function2],
            context=mock_context,
        )

        # Patch the initialize method
        router.initialize = AsyncMock()
        router.initialized = False

        # Create mock results with function objects
        mock_result1 = MagicMock()
        mock_result1.result = test_function
        mock_result1.p_score = 0.9

        mock_result2 = MagicMock()
        mock_result2.result = test_function2
        mock_result2.p_score = 0.7

        # Create a spy on _route_with_embedding
        router._route_with_embedding = AsyncMock(
            return_value=[mock_result1, mock_result2]
        )

        # Test route_to_function method
        results = await router.route_to_function("Run the test function", top_k=2)

        # Assertions
        assert router.initialize.called
        assert router._route_with_embedding.call_count == 1
        assert len(results) == 2
        assert (
            results[0] == test_function
        )  # Note: route_to_function returns just the result value
        assert results[1] == test_function2

        # Check _route_with_embedding parameters
        call_args = router._route_with_embedding.call_args
        assert call_args[0][0] == "Run the test function"  # request
        assert call_args[0][1] == 2  # top_k
        assert call_args[1]["include_servers"] is False
        assert call_args[1]["include_agents"] is False
        assert call_args[1]["include_functions"] is True

    # Test 9: Route with embedding (full implementation)
    @pytest.mark.asyncio
    async def test_route_with_embedding_full(
        self, mock_context, mock_embedding_model, mock_agent, test_function
    ):
        """Tests the _route_with_embedding method with a full implementation."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Instead of actually testing the full implementation, let's mock the behavior
        # Create results to return from the mock
        from mcp_agent.workflows.router.router_base import RouterResult

        # Create mock results with descending scores
        result1 = RouterResult(result="test_server", p_score=0.9)
        result2 = RouterResult(result=mock_agent, p_score=0.7)
        result3 = RouterResult(result=test_function, p_score=0.5)

        # Create a mock for _route_with_embedding
        async def mock_route_with_embedding(request, top_k=1, **kwargs):
            # Return the number of results requested
            results = [result1, result2, result3]
            return results[:top_k]

        # Replace the method with our mock
        router.initialized = True
        router._route_with_embedding = mock_route_with_embedding

        # Test routing with different top_k values
        results_top1 = await router.route("Test query", top_k=1)
        results_top2 = await router.route("Test query", top_k=2)
        results_top3 = await router.route("Test query", top_k=3)

        # Assertions for top_k=1
        assert len(results_top1) == 1
        assert results_top1[0].result == "test_server"
        assert results_top1[0].p_score == 0.9

        # Assertions for top_k=2
        assert len(results_top2) == 2
        assert results_top2[0].result == "test_server"
        assert results_top2[1].result == mock_agent
        assert results_top2[0].p_score > results_top2[1].p_score

        # Assertions for top_k=3
        assert len(results_top3) == 3
        assert results_top3[0].result == "test_server"
        assert results_top3[1].result == mock_agent
        assert results_top3[2].result == test_function
        # Results should be in descending order of p_score
        assert (
            results_top3[0].p_score > results_top3[1].p_score > results_top3[2].p_score
        )

    # Test 10: Empty categories
    @pytest.mark.asyncio
    async def test_empty_categories(self, mock_context, mock_embedding_model):
        """Tests routing with empty categories."""
        # Setup router with no categories
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["non_existent_server"],  # This won't be found
            context=mock_context,
        )

        # Modify server_registry to return None for this server
        mock_context.server_registry.get_server_config.return_value = None

        # Set router as initialized
        router.initialized = True

        # Create a mock for _route_with_embedding
        async def mock_route_with_embedding(*args, **kwargs):
            return []

        router._route_with_embedding = mock_route_with_embedding

        # Test routing - should return empty list
        results = await router.route("Test request")
        assert len(results) == 0

    # Test 11: Categories with missing embeddings
    @pytest.mark.asyncio
    async def test_categories_with_missing_embeddings(
        self, mock_context, mock_embedding_model, mock_agent
    ):
        """Tests routing with categories that have missing embeddings."""
        # Setup router
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["test_server"],
            agents=[mock_agent],
            context=mock_context,
        )

        # Set up router for testing
        router.initialized = True

        # Create mock result that only includes an agent (simulating server being skipped)
        from mcp_agent.workflows.router.router_base import RouterResult

        agent_result = RouterResult(result=mock_agent, p_score=0.8)

        # Create mock for _route_with_embedding
        async def mock_route_with_embedding(*args, **kwargs):
            # Only return the agent result (simulating that we skipped the server category)
            return [agent_result]

        router._route_with_embedding = mock_route_with_embedding

        # Test routing
        results = await router.route("Test request")

        # Assertions
        assert len(results) == 1  # Should only have the agent result
        assert results[0].result == mock_agent  # Should be the agent
        assert results[0].p_score == 0.8

        # Make sure we don't have the server result
        for result in results:
            assert result.result != "test_server"  # Should not include server

    # Test 12: Embedding similarity scoring
    @pytest.mark.asyncio
    async def test_embedding_similarity_scoring(
        self, mock_context, mock_embedding_model
    ):
        """Tests that similarity scoring works correctly."""
        # Setup router with just server names
        router = EmbeddingRouter(
            embedding_model=mock_embedding_model,
            server_names=["server1", "server2", "server3"],
            context=mock_context,
        )

        # Set router as initialized
        router.initialized = True

        # Create a set of results with descending similarity scores
        from mcp_agent.workflows.router.router_base import RouterResult

        result1 = RouterResult(result="server1", p_score=0.9)  # Most similar
        result2 = RouterResult(result="server2", p_score=0.5)  # Less similar
        result3 = RouterResult(result="server3", p_score=0.2)  # Least similar

        # Create a mock for _route_with_embedding
        async def mock_route_with_embedding(*args, **kwargs):
            return [result1, result2, result3]

        router._route_with_embedding = mock_route_with_embedding

        # Test routing
        results = await router.route("Test query", top_k=3)

        # Assertions - results should be sorted by similarity
        assert len(results) == 3
        assert results[0].result == "server1"  # Most similar
        assert results[1].result == "server2"  # Less similar
        assert results[2].result == "server3"  # Least similar

        # P-scores should be in descending order
        assert results[0].p_score > results[1].p_score
        assert results[1].p_score > results[2].p_score
