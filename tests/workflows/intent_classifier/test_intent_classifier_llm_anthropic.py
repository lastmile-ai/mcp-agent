from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

from mcp_agent.workflows.intent_classifier.intent_classifier_base import (
    IntentClassificationResult,
)
from mcp_agent.workflows.intent_classifier.intent_classifier_llm import (
    LLMIntentClassificationResult,
    StructuredIntentResponse,
)
from mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic import (
    AnthropicLLMIntentClassifier,
    CLASSIFIER_SYSTEM_INSTRUCTION,
)


class MockAnthropicAugmentedLLM:
    """Mock Anthropic augmented LLM for testing"""

    def __init__(
        self, instruction: str = "", context: Optional["Context"] = None, **kwargs
    ):
        self.instruction = instruction
        self.context = context
        self.initialized = False
        self.kwargs = kwargs

    async def initialize(self):
        self.initialized = True


class TestAnthropicLLMIntentClassifier:
    """
    Tests for the AnthropicLLMIntentClassifier class.
    """

    @pytest.fixture
    def setup_anthropic_context(self, mock_context):
        """Add Anthropic-specific configuration to the mock context"""
        mock_context.config.anthropic = MagicMock()
        mock_context.config.anthropic.api_key = "test_api_key"
        mock_context.config.anthropic.default_model = "claude-3-7-sonnet-latest"
        return mock_context

    # Test 1: Basic initialization
    def test_initialization(self, test_intents, setup_anthropic_context):
        """
        Tests basic initialization of the classifier.
        """
        # Initialize with mock LLM model
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            classifier = AnthropicLLMIntentClassifier(
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Assertions
            assert classifier is not None
            assert len(classifier.intents) == len(test_intents)
            assert isinstance(classifier.llm, MockAnthropicAugmentedLLM)
            assert classifier.initialized is False
            assert classifier.llm.instruction == CLASSIFIER_SYSTEM_INSTRUCTION

    # Test 2: Initialization with custom classification instruction
    def test_initialization_with_custom_instruction(
        self, test_intents, setup_anthropic_context
    ):
        """
        Tests initialization with a custom classification instruction.
        """
        custom_instruction = "Custom classification instruction for testing"

        # Initialize classifier with custom instruction
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            classifier = AnthropicLLMIntentClassifier(
                intents=test_intents,
                classification_instruction=custom_instruction,
                context=setup_anthropic_context,
            )

            # Assertions
            assert classifier is not None
            assert classifier.classification_instruction == custom_instruction

    # Test 3: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(self, test_intents, setup_anthropic_context):
        """
        Tests the factory method for creating and initializing a classifier.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create classifier using factory method
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Assertions
            assert classifier is not None
            assert classifier.initialized is True
            assert len(classifier.intents) == len(test_intents)
            assert isinstance(classifier.llm, MockAnthropicAugmentedLLM)

    # Test 4: Factory method with custom classification instruction
    @pytest.mark.asyncio
    async def test_create_with_custom_instruction(
        self, test_intents, setup_anthropic_context
    ):
        """
        Tests the factory method with a custom classification instruction.
        """
        custom_instruction = "Custom classification instruction for testing"

        # Create classifier using factory method with custom instruction
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                classification_instruction=custom_instruction,
                context=setup_anthropic_context,
            )

            # Assertions
            assert classifier is not None
            assert classifier.initialized is True
            assert classifier.classification_instruction == custom_instruction

    # Test 5: Classification functionality
    @pytest.mark.asyncio
    async def test_classification(self, test_intents, setup_anthropic_context):
        """
        Tests the classification functionality.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create and initialize classifier
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Mock the generate_structured method to return test results
            mock_response = StructuredIntentResponse(
                classifications=[
                    LLMIntentClassificationResult(
                        intent="greeting",
                        p_score=0.9,
                        confidence="high",
                        reasoning="Clear greeting pattern detected",
                    ),
                    LLMIntentClassificationResult(
                        intent="help",
                        p_score=0.7,
                        confidence="medium",
                        reasoning="Some help-seeking indicators",
                    ),
                ]
            )

            # Patch the LLM's generate_structured method
            classifier.llm.generate_structured = AsyncMock(return_value=mock_response)

            # Perform classification with explicit top_k parameter
            results = await classifier.classify("Hello, how can you help me?", top_k=2)

            # Assertions
            assert isinstance(results, list)
            assert len(results) == 2  # Ensure we get 2 results when top_k=2
            assert all(
                isinstance(result, IntentClassificationResult) for result in results
            )
            assert results[0].intent == "greeting"
            assert results[0].p_score == 0.9
            assert results[1].intent == "help"
            assert results[1].p_score == 0.7

    # Test 6: Classification with specific intents
    @pytest.mark.asyncio
    async def test_classification_with_specific_intents(
        self, test_intents, setup_anthropic_context
    ):
        """
        Tests the classification with specific input phrases.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create and initialize classifier
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Create separate mock responses for different inputs
            greeting_response = StructuredIntentResponse(
                classifications=[
                    LLMIntentClassificationResult(
                        intent="greeting",
                        p_score=0.95,
                        confidence="high",
                        reasoning="Clear greeting pattern",
                    )
                ]
            )

            help_response = StructuredIntentResponse(
                classifications=[
                    LLMIntentClassificationResult(
                        intent="help",
                        p_score=0.85,
                        confidence="medium",
                        reasoning="Help request detected",
                    )
                ]
            )

            empty_response = StructuredIntentResponse(classifications=[])

            # Create a mock that will be called multiple times with different return values
            mock_generate_structured = AsyncMock()

            # Configure the mock to return different responses for different calls
            mock_generate_structured.side_effect = [
                greeting_response,  # First call (for "Hello there")
                help_response,  # Second call (for "I need some help")
                empty_response,  # Third call (for "Random text with no intent")
            ]

            # Apply the mock
            classifier.llm.generate_structured = mock_generate_structured

            # Test with greeting input
            greeting_results = await classifier.classify("Hello there")
            assert len(greeting_results) == 1
            assert greeting_results[0].intent == "greeting"
            assert greeting_results[0].p_score == 0.95

            # Test with help input
            help_results = await classifier.classify("I need some help")
            assert len(help_results) == 1
            assert help_results[0].intent == "help"
            assert help_results[0].p_score == 0.85

            # Test with unmatched input
            no_match_results = await classifier.classify("Random text with no intent")
            assert len(no_match_results) == 0

    # Test 7: Empty intents
    def test_empty_intents(self, setup_anthropic_context):
        """
        Tests initialization with empty intents list.
        """
        # Mock the LLM to avoid API calls
        with (
            patch(
                "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
                MockAnthropicAugmentedLLM,
            ),
            pytest.raises(ValueError),
        ):
            # Initialize with empty intents list
            _ = AnthropicLLMIntentClassifier(
                intents=[],
                context=setup_anthropic_context,
            )

    # Test 8: Initialization process
    @pytest.mark.asyncio
    async def test_initialization_process(self, test_intents, setup_anthropic_context):
        """
        Tests the initialization process.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create classifier
            classifier = AnthropicLLMIntentClassifier(
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Define what happens when initialize is called
            async def mock_initialize():
                classifier.initialized = True
                classifier.llm.initialized = True

            # Apply the mock
            classifier.initialize = AsyncMock(side_effect=mock_initialize)

            # Initialize the classifier
            await classifier.initialize()

            # Assertions
            assert classifier.initialized is True
            assert classifier.llm.initialized is True

    # Test 9: Generate context format
    def test_generate_context(self, test_intents, setup_anthropic_context):
        """
        Tests the _generate_context helper method format.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create classifier
            classifier = AnthropicLLMIntentClassifier(
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Generate context
            context = classifier._generate_context()

            # Assertions
            assert isinstance(context, str)
            assert len(context) > 0

            # Check that all intent names are in the context
            for intent in test_intents:
                assert intent.name in context
                assert intent.description in context

                # Check that examples are included
                for example in intent.examples:
                    assert example in context

    # Test 10: Structured response handling
    @pytest.mark.asyncio
    async def test_structured_response_handling(
        self, test_intents, setup_anthropic_context
    ):
        """
        Tests that structured responses from the LLM are correctly processed.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create and initialize classifier
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Mock the generate_structured method on the LLM
            mock_response = StructuredIntentResponse(
                classifications=[
                    LLMIntentClassificationResult(
                        intent="greeting",
                        p_score=0.85,
                        confidence="high",
                        reasoning="Clear greeting pattern detected",
                    ),
                    LLMIntentClassificationResult(
                        intent="help",
                        p_score=0.65,
                        confidence="medium",
                        reasoning="Some help-seeking indicators",
                    ),
                ]
            )

            classifier.llm.generate_structured = AsyncMock(return_value=mock_response)

            # Test classification
            results = await classifier.classify("Hello, can you help me?", top_k=2)

            # Assertions
            assert len(results) == 2
            assert results[0].intent == "greeting"
            assert results[0].p_score == 0.85
            assert results[0].confidence == "high"
            assert results[0].reasoning == "Clear greeting pattern detected"
            assert results[1].intent == "help"
            assert results[1].p_score == 0.65

            # Verify generate_structured was called with the right parameters
            assert classifier.llm.generate_structured.called

            # Test with top_k=1 to ensure limit works
            results_limited = await classifier.classify(
                "Hello, can you help me?", top_k=1
            )
            assert len(results_limited) == 1
            assert results_limited[0].intent == "greeting"

    # Test 11: Empty response handling
    @pytest.mark.asyncio
    async def test_empty_response_handling(self, test_intents, setup_anthropic_context):
        """
        Tests handling of empty responses from the LLM.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create and initialize classifier
            mock_llm = MockAnthropicAugmentedLLM(context=setup_anthropic_context)
            classifier = await AnthropicLLMIntentClassifier.create(
                llm=mock_llm,
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Mock the generate_structured method to return empty response
            classifier.llm.generate_structured = AsyncMock(
                return_value=StructuredIntentResponse(classifications=[])
            )

            # Test classification with empty response
            results = await classifier.classify("Completely unrelated text")

            # Assertions
            assert isinstance(results, list)
            assert len(results) == 0

    # Test 12: Multiple initialization calls
    @pytest.mark.asyncio
    async def test_multiple_initialization(self, test_intents, setup_anthropic_context):
        """
        Tests that multiple initialization calls don't re-initialize if already initialized.
        """
        # Mock the LLM to avoid API calls
        with patch(
            "mcp_agent.workflows.intent_classifier.intent_classifier_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            # Create classifier
            classifier = AnthropicLLMIntentClassifier(
                intents=test_intents,
                context=setup_anthropic_context,
            )

            # Mock the initialize method
            real_initialize = classifier.initialize
            classifier.initialize = AsyncMock(wraps=real_initialize)

            # Initialize the classifier
            await classifier.initialize()
            assert classifier.initialize.call_count == 1
            assert classifier.initialized is True

            # Call initialize again
            await classifier.initialize()
            assert (
                classifier.initialize.call_count == 2
            )  # Called, but should short-circuit internally
            assert classifier.initialized is True
