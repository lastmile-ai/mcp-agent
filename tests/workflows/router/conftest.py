import pytest
from unittest.mock import AsyncMock, MagicMock
import numpy as np
from typing import List

from mcp_agent.core.context import Context
from mcp_agent.workflows.embedding.embedding_base import FloatArray, EmbeddingModel
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.workflows.router.router_base import (
    RouterCategory,
    ServerRouterCategory,
    AgentRouterCategory,
)


@pytest.fixture
def mock_context():
    """
    Returns a mock Context instance for testing.
    """
    mock = MagicMock(spec=Context)
    # Tracing disabled by default in unit tests
    mock.tracer = None
    mock.tracing_enabled = False

    # Executor with a stable uuid for AugmentedLLM name generation
    mock.executor = MagicMock()
    mock.executor.uuid = MagicMock(return_value="test-uuid")

    # Setup configuration for different providers
    mock.config = MagicMock()

    # OpenAI config
    mock.config.openai = MagicMock()
    mock.config.openai.api_key = "test_openai_key"
    mock.config.openai.default_model = "gpt-4o"

    # Anthropic config
    mock.config.anthropic = MagicMock()
    mock.config.anthropic.api_key = "test_anthropic_key"
    mock.config.anthropic.default_model = "claude-3-7-sonnet-latest"

    # Cohere config
    mock.config.cohere = MagicMock()
    mock.config.cohere.api_key = "test_cohere_key"

    # Setup server registry
    mock.server_registry = MagicMock()

    # Create a proper server config object that returns string values
    class ServerConfig:
        def __init__(self):
            self.name = "test_server"
            self.description = "A test server for routing"
            self.embedding = None

    server_config = ServerConfig()
    mock.server_registry.get_server_config = MagicMock(return_value=server_config)

    # Provide a model selector used by AugmentedLLM.select_model if invoked
    mock.model_selector = MagicMock()
    mock.model_selector.select_model = MagicMock(return_value="test-model")

    # Token counter not used in these tests
    mock.token_counter = None

    return mock


@pytest.fixture
def mock_agent():
    """
    Returns a real Agent instance for testing.
    """
    from mcp_agent.agents.agent import Agent

    agent = Agent(
        name="test_agent",
        instruction="This is a test agent instruction",
        server_names=["test_server"],
    )
    return agent


@pytest.fixture
def mock_llm():
    """
    Returns a mock AugmentedLLM instance for testing.
    """
    mock = MagicMock(spec=AugmentedLLM)
    mock.generate = AsyncMock()
    mock.generate_str = AsyncMock()
    mock.generate_structured = AsyncMock()
    return mock


@pytest.fixture
def mock_embedding_model():
    """
    Returns a mock EmbeddingModel instance for testing.
    """
    mock = MagicMock(spec=EmbeddingModel)

    # Generate deterministic but different embeddings for testing
    async def embed_side_effect(data: List[str]) -> FloatArray:
        embedding_dim = 1536
        embeddings = np.ones((len(data), embedding_dim), dtype=np.float32)
        for i in range(len(data)):
            # Simple hashing to create different embeddings for different strings
            seed = sum(ord(c) for c in data[i])
            np.random.seed(seed)
            embeddings[i] = np.random.rand(embedding_dim).astype(np.float32)
        return embeddings

    mock.embed = AsyncMock(side_effect=embed_side_effect)
    mock.embedding_dim = 1536

    return mock


@pytest.fixture
def test_function():
    """
    Returns a test function for router testing.
    """

    def test_function(input_text: str) -> str:
        """A test function that echoes the input."""
        return f"Echo: {input_text}"

    return test_function


@pytest.fixture
def test_router_categories(mock_agent, test_function):
    """
    Returns test router categories for testing.
    """
    # Server category
    server_category = ServerRouterCategory(
        name="test_server",
        description="A test server for routing",
        category="test_server",
        tools=[],  # Using empty list for tools to avoid validation issues
    )

    # Agent category
    agent_category = AgentRouterCategory(
        name="test_agent",
        description="A test agent for routing",
        category=mock_agent,
        servers=[server_category],
    )

    # Function category
    function_category = RouterCategory(
        name="test_function",
        description="A test function for routing",
        category=test_function,
    )

    return {
        "server_category": server_category,
        "agent_category": agent_category,
        "function_category": function_category,
    }
