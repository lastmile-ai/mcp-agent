import pytest
from unittest.mock import MagicMock
import numpy as np
from typing import List

from mcp_agent.workflows.embedding.embedding_base import FloatArray
from mcp_agent.workflows.intent_classifier.intent_classifier_base import Intent


@pytest.fixture
def mock_context():
    """Common mock context fixture usable by all intent classifier tests"""
    mock_context = MagicMock()
    mock_context.config = MagicMock()

    # Setup OpenAI-specific config for embedding models
    mock_context.config.openai = MagicMock()
    mock_context.config.openai.api_key = "test_api_key"

    # Setup Cohere-specific config for embedding models
    mock_context.config.cohere = MagicMock()
    mock_context.config.cohere.api_key = "test_api_key"

    return mock_context


@pytest.fixture
def test_intents():
    """Common test intents fixture"""
    return [
        Intent(
            name="greeting",
            description="A friendly greeting",
            examples=["Hello", "Hi there", "Good morning"],
        ),
        Intent(
            name="farewell",
            description="A friendly farewell",
            examples=["Goodbye", "See you later", "Take care"],
        ),
        Intent(
            name="help",
            description="A request for help or assistance",
            examples=["Can you help me?", "I need assistance", "How do I use this?"],
        ),
    ]


class MockEmbeddingModel:
    """Mock embedding model for testing intent classifiers"""

    def __init__(self):
        self._embedding_dim = 1536

    async def embed(self, data: List[str]) -> FloatArray:
        """
        Generate deterministic but different embeddings for testing
        """
        embeddings = np.ones((len(data), self._embedding_dim), dtype=np.float32)
        for i in range(len(data)):
            # Simple hashing to create different embeddings for different strings
            seed = sum(ord(c) for c in data[i])
            np.random.seed(seed)
            embeddings[i] = np.random.rand(self._embedding_dim).astype(np.float32)
        return embeddings

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim


@pytest.fixture
def mock_embedding_model():
    """Fixture that provides a mock embedding model"""
    return MockEmbeddingModel()
