from unittest.mock import patch
import numpy as np
import pytest
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

from mcp_agent.workflows.embedding.embedding_base import FloatArray
from mcp_agent.workflows.intent_classifier.intent_classifier_base import (
    IntentClassificationResult,
)
from mcp_agent.workflows.intent_classifier.intent_classifier_embedding import (
    EmbeddingIntent,
)
from mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai import (
    OpenAIEmbeddingIntentClassifier,
)


class MockOpenAIEmbeddingModel:
    """Mock OpenAI embedding model for testing"""

    def __init__(
        self, model: str = "text-embedding-3-small", context: Optional["Context"] = None
    ):
        self._embedding_dim = 1536
        self.model = model
        self.context = context

    async def embed(self, data: List[str]) -> FloatArray:
        # Return deterministic embeddings for testing
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


class TestOpenAIEmbeddingIntentClassifier:
    """
    Tests for the OpenAIEmbeddingIntentClassifier class.
    """

    # Test 1: Basic initialization
    def test_initialization(self, test_intents, mock_context):
        """
        Tests basic initialization of the classifier.
        """
        # Initialize with mock embedding model
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            classifier = OpenAIEmbeddingIntentClassifier(
                intents=test_intents,
                context=mock_context,
            )

            # Assertions
            assert classifier is not None
            assert len(classifier.intents) == len(test_intents)
            assert isinstance(classifier.embedding_model, MockOpenAIEmbeddingModel)
            assert classifier.initialized is False

    # Test 2: Initialization with custom embedding model
    def test_initialization_with_custom_model(self, test_intents, mock_context):
        """
        Tests initialization with a custom embedding model.
        """
        # Create a custom embedding model
        custom_model = MockOpenAIEmbeddingModel(model="text-embedding-3-large")

        # Initialize classifier with the custom model
        classifier = OpenAIEmbeddingIntentClassifier(
            intents=test_intents,
            embedding_model=custom_model,
            context=mock_context,
        )

        # Assertions
        assert classifier is not None
        assert classifier.embedding_model == custom_model
        assert classifier.embedding_model.model == "text-embedding-3-large"

    # Test 3: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(self, test_intents, mock_context):
        """
        Tests the factory method for creating and initializing a classifier.
        """
        # Mock the embedding model to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            # Create classifier using factory method
            classifier = await OpenAIEmbeddingIntentClassifier.create(
                intents=test_intents,
                context=mock_context,
            )

            # Assertions
            assert classifier is not None
            assert classifier.initialized is True
            assert len(classifier.intents) == len(test_intents)
            assert isinstance(classifier.embedding_model, MockOpenAIEmbeddingModel)

    # Test 4: Factory method with custom embedding model
    @pytest.mark.asyncio
    async def test_create_with_custom_model(self, test_intents, mock_context):
        """
        Tests the factory method with a custom embedding model.
        """
        # Create a custom embedding model
        custom_model = MockOpenAIEmbeddingModel(model="text-embedding-3-large")

        # Create classifier using factory method with custom model
        classifier = await OpenAIEmbeddingIntentClassifier.create(
            intents=test_intents,
            embedding_model=custom_model,
            context=mock_context,
        )

        # Assertions
        assert classifier is not None
        assert classifier.initialized is True
        assert classifier.embedding_model == custom_model
        assert classifier.embedding_model.model == "text-embedding-3-large"

    # Test 5: Classification functionality
    @pytest.mark.asyncio
    async def test_classification(self, test_intents, mock_context):
        """
        Tests the classification functionality.
        """
        # Mock the embedding model to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            # Create and initialize classifier
            classifier = await OpenAIEmbeddingIntentClassifier.create(
                intents=test_intents,
                context=mock_context,
            )

            # Perform classification
            results = await classifier.classify("Hello, how are you?", top_k=3)

            # Assertions
            assert isinstance(results, list)
            assert len(results) == 3  # We asked for top 3 results
            assert all(
                isinstance(result, IntentClassificationResult) for result in results
            )
            # The top intent is likely to be "greeting" due to our mock embedding implementation
            assert results[0].intent in [intent.name for intent in test_intents]
            assert (
                0 <= results[0].p_score <= 1
            )  # Confidence score should be between 0 and 1

    # Test 6: Classification with top_k parameter
    @pytest.mark.asyncio
    async def test_classification_with_top_k(self, test_intents, mock_context):
        """
        Tests the classification with different top_k values.
        """
        # Mock the embedding model to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            # Create and initialize classifier
            classifier = await OpenAIEmbeddingIntentClassifier.create(
                intents=test_intents,
                context=mock_context,
            )

            # Test with top_k=1
            results_1 = await classifier.classify("Hello", top_k=1)
            assert len(results_1) == 1

            # Test with top_k=2
            results_2 = await classifier.classify("Hello", top_k=2)
            assert len(results_2) == 2

            # Test with top_k greater than the number of intents
            results_3 = await classifier.classify("Hello", top_k=10)
            assert len(results_3) == len(
                test_intents
            )  # Should be capped at the number of intents

    # Test 7: Empty intents
    def test_empty_intents(self, mock_context):
        """
        Tests initialization with empty intents list.
        """
        # Mock the embedding model to avoid API calls
        with (
            patch(
                "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
                MockOpenAIEmbeddingModel,
            ),
            pytest.raises(ValueError),
        ):
            # Initialize with empty intents list
            _ = OpenAIEmbeddingIntentClassifier(
                intents=[],
                context=mock_context,
            )

    # Test 8: Initialization process
    @pytest.mark.asyncio
    async def test_initialization_process(self, test_intents, mock_context):
        """
        Tests the initialization process that creates embeddings for intents.
        """
        # Mock the embedding model to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            # Create classifier
            classifier = OpenAIEmbeddingIntentClassifier(
                intents=test_intents,
                context=mock_context,
            )

            # Initialize the classifier
            await classifier.initialize()

            # Assertions
            assert classifier.initialized is True

            # Check that intents now have embeddings
            for intent_name, intent in classifier.intents.items():
                assert isinstance(intent, EmbeddingIntent)
                assert intent.embedding is not None
                assert intent.embedding.shape == (
                    1536,
                )  # The embedding dimension for our mock

    # Test 9: Multiple initialization calls
    @pytest.mark.asyncio
    async def test_multiple_initialization(self, test_intents, mock_context):
        """
        Tests that multiple initialization calls don't re-compute embeddings.
        """
        # Mock the embedding model to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_embedding_openai.OpenAIEmbeddingModel",
            MockOpenAIEmbeddingModel,
        ):
            # Create classifier
            classifier = OpenAIEmbeddingIntentClassifier(
                intents=test_intents,
                context=mock_context,
            )

            # Create a spy on the embed method
            with patch.object(
                classifier.embedding_model,
                "embed",
                wraps=classifier.embedding_model.embed,
            ) as embed_spy:
                # Initialize the classifier
                await classifier.initialize()
                assert (
                    embed_spy.call_count > 0
                )  # Should be called for initial embeddings

                # Reset the spy's call count
                embed_spy.reset_mock()

                # Call initialize again
                await classifier.initialize()
                embed_spy.assert_not_called()  # Should not be called again
