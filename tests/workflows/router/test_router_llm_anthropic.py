import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

from mcp_agent.workflows.router.router_llm import LLMRouter
from mcp_agent.workflows.router.router_llm_anthropic import (
    AnthropicLLMRouter,
    ROUTING_SYSTEM_INSTRUCTION,
)


class MockAnthropicAugmentedLLM:
    """Mock AnthropicAugmentedLLM for testing."""

    def __init__(
        self, instruction: str = "", context: Optional["Context"] = None, **kwargs
    ):
        self.instruction = instruction
        self.context = context
        self.initialized = False
        self.kwargs = kwargs

    async def initialize(self):
        self.initialized = True

    async def generate(self, message, **kwargs):
        """Mock generate method."""
        return []

    async def generate_str(self, message, **kwargs):
        """Mock generate_str method."""
        return ""

    async def generate_structured(self, message, response_model, **kwargs):
        """Mock generate_structured method."""
        return response_model()


class TestAnthropicLLMRouter:
    """Tests for the AnthropicLLMRouter class."""

    @pytest.fixture
    def setup_anthropic_context(self, mock_context):
        """Add Anthropic-specific configuration to the mock context."""
        mock_context.config.anthropic = MagicMock()
        mock_context.config.anthropic.api_key = "test_api_key"
        mock_context.config.anthropic.default_model = "claude-3-7-sonnet-latest"
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return mock_context

    # Test 1: Basic initialization
    def test_initialization(self, setup_anthropic_context, mock_agent, test_function):
        """Tests basic initialization of the router."""
        # Initialize router with mock LLM
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            router = AnthropicLLMRouter(
                server_names=["test_server"],
                agents=[mock_agent],
                functions=[test_function],
                context=setup_anthropic_context,
            )

            # Assertions
            assert router is not None
            assert isinstance(router, LLMRouter)
            assert isinstance(router.llm, MockAnthropicAugmentedLLM)
            assert router.llm.instruction == ROUTING_SYSTEM_INSTRUCTION
            assert router.server_names == ["test_server"]
            assert router.agents == [mock_agent]
            assert router.functions == [test_function]
            assert router.context == setup_anthropic_context
            assert router.initialized is False

    # Test 2: Initialization with custom instruction
    def test_initialization_with_custom_instruction(
        self, setup_anthropic_context, mock_agent
    ):
        """Tests initialization with a custom instruction."""
        custom_instruction = "Custom routing instruction for testing"

        # Initialize router with custom instruction
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            router = AnthropicLLMRouter(
                server_names=["test_server"],
                agents=[mock_agent],
                routing_instruction=custom_instruction,
                context=setup_anthropic_context,
            )

            # Assertions
            assert router is not None
            assert router.routing_instruction == custom_instruction

    # Test 3: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(self, setup_anthropic_context, mock_agent):
        """Tests the factory method for creating and initializing a router."""
        # Create router using factory method with mock LLM
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            router = await AnthropicLLMRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_anthropic_context,
            )

            # Assertions
            assert router is not None
            assert router.initialized is True
            assert isinstance(router.llm, MockAnthropicAugmentedLLM)
            assert router.llm.instruction == ROUTING_SYSTEM_INSTRUCTION
            assert router.server_names == ["test_server"]
            assert router.agents == [mock_agent]
            assert router.context == setup_anthropic_context
            assert len(router.server_categories) == 1
            assert len(router.agent_categories) == 1

    # Test 4: Factory method with custom instruction
    @pytest.mark.asyncio
    async def test_create_with_custom_instruction(
        self, setup_anthropic_context, mock_agent
    ):
        """Tests the factory method with a custom instruction."""
        custom_instruction = "Custom routing instruction for testing"

        # Create router using factory method with custom instruction
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM",
            MockAnthropicAugmentedLLM,
        ):
            router = await AnthropicLLMRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                routing_instruction=custom_instruction,
                context=setup_anthropic_context,
            )

            # Assertions
            assert router is not None
            assert router.initialized is True
            assert router.routing_instruction == custom_instruction

    # Test 5: Anthropic LLM is correctly configured
    def test_anthropic_llm_configuration(self, setup_anthropic_context):
        """Tests that AnthropicAugmentedLLM is correctly configured."""
        # Initialize router with real AnthropicAugmentedLLM class
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM"
        ) as mock_llm_class:
            mock_llm_class.return_value = MagicMock()

            _router = AnthropicLLMRouter(
                server_names=["test_server"],
                context=setup_anthropic_context,
            )

            # Assertions
            mock_llm_class.assert_called_once()

            # Check that the LLM was initialized with the correct instruction
            call_args = mock_llm_class.call_args
            assert call_args[1]["instruction"] == ROUTING_SYSTEM_INSTRUCTION
            assert call_args[1]["context"] == setup_anthropic_context

    # Test 6: Routing functionality (integration with LLMRouter)
    @pytest.mark.asyncio
    async def test_routing_functionality(self, setup_anthropic_context, mock_agent):
        """Tests that the routing functionality works correctly."""
        # Create a mock LLM that returns a proper structured response
        from mcp_agent.workflows.router.router_llm import (
            StructuredResponse,
            StructuredResponseCategory,
        )

        mock_llm = MagicMock()
        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="test_server",
                    confidence="high",
                    reasoning="Test reasoning",
                )
            ]
        )
        mock_llm.generate_structured = AsyncMock(return_value=mock_response)
        mock_llm.initialize = AsyncMock()

        # Initialize router with our mocked LLM
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM",
            return_value=mock_llm,
        ):
            router = await AnthropicLLMRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_anthropic_context,
            )

            # Create a spy on _route_with_llm method
            original_route_with_llm = router._route_with_llm
            router._route_with_llm = AsyncMock(wraps=original_route_with_llm)

            # Test routing
            result = await router.route("Test request")

            # Assertions
            assert router._route_with_llm.called
            call_args = router._route_with_llm.call_args
            assert call_args[0][0] == "Test request"
            assert len(result) == 1
            assert result[0].result == "test_server"
            assert result[0].confidence == "high"
            assert result[0].reasoning == "Test reasoning"

    # Test 7: Full routing flow
    @pytest.mark.asyncio
    async def test_full_routing_flow(self, setup_anthropic_context, mock_agent):
        """Tests the full routing flow from request to LLM to result."""
        # Create a mock response from generate_structured
        from mcp_agent.workflows.router.router_llm import (
            StructuredResponse,
            StructuredResponseCategory,
        )

        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="test_server",
                    confidence="high",
                    reasoning="Matches server capabilities",
                )
            ]
        )

        # Initialize router with mock LLM that returns our mocked response
        with patch(
            "mcp_agent.workflows.router.router_llm_anthropic.AnthropicAugmentedLLM"
        ) as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.generate_structured = AsyncMock(return_value=mock_response)
            mock_llm_class.return_value = mock_llm

            # Create and initialize router
            router = await AnthropicLLMRouter.create(
                server_names=["test_server"],
                agents=[mock_agent],
                context=setup_anthropic_context,
            )

            # Test routing
            results = await router.route("Test request")

            # Assertions
            assert mock_llm.generate_structured.called
            assert len(results) == 1
            assert results[0].result == "test_server"
            assert results[0].confidence == "high"
            assert results[0].reasoning == "Matches server capabilities"
