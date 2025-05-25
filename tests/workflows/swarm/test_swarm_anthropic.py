import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.swarm.swarm_anthropic import AnthropicSwarm
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestAnthropicSwarm:
    """Tests for the AnthropicSwarm class."""

    @pytest.fixture
    def mock_anthropic_swarm(self, mock_swarm_agent):
        """Create a mock AnthropicSwarm instance."""
        swarm = AnthropicSwarm(agent=mock_swarm_agent)

        # Mock the logger
        swarm.logger = MagicMock()

        return swarm

    @pytest.mark.asyncio
    async def test_anthropic_swarm_initialization(self, mock_swarm_agent):
        """Test AnthropicSwarm initialization."""
        # Create an AnthropicSwarm instance
        context_variables = {"var1": "value1", "var2": "value2"}
        swarm = AnthropicSwarm(
            agent=mock_swarm_agent, context_variables=context_variables
        )

        # Assert swarm properties
        assert swarm.agent == mock_swarm_agent
        assert swarm.context_variables == context_variables
        assert swarm.instruction == mock_swarm_agent.instruction

    @pytest.mark.asyncio
    async def test_anthropic_swarm_generate_with_default_params(
        self, mock_anthropic_swarm
    ):
        """Test AnthropicSwarm generate method with default parameters."""
        # Setup
        message = "Test message"
        mock_response = MagicMock()

        # Ensure we only make one iteration
        mock_anthropic_swarm.should_continue = MagicMock(side_effect=[True, False])

        # Mock the super().generate method to return our mock response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_anthropic.AnthropicAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate with default parameters
            result = await mock_anthropic_swarm.generate(message)

            # Assert the result is our mock response
            assert result == mock_response

            # Check that AnthropicAugmentedLLM.generate was called with the right parameters
            last_call_kwargs = mock_generate.call_args_list[-1][1]
            # Should only iterate once since we forced should_continue to return False
            assert last_call_kwargs["request_params"].max_iterations == 1
            # Should use the original message since we're only making one call
            assert last_call_kwargs["message"] == message
            # Should use the claude-3-5-sonnet-20241022 model by default
            assert (
                last_call_kwargs["request_params"].model == "claude-3-5-sonnet-20241022"
            )

    @pytest.mark.asyncio
    async def test_anthropic_swarm_generate_with_custom_params(
        self, mock_anthropic_swarm
    ):
        """Test AnthropicSwarm generate method with custom parameters."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(
            model="claude-3-haiku", maxTokens=4096, max_iterations=3
        )
        mock_response = MagicMock()

        # Mock the super().generate method to return our mock response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_anthropic.AnthropicAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate with custom parameters
            result = await mock_anthropic_swarm.generate(message, custom_params)

            # Assert the result is our mock response
            assert result == mock_response

            # Check that AnthropicAugmentedLLM.generate was called with the right parameters
            last_call_kwargs = mock_generate.call_args_list[-1][1]
            # Should only iterate once since max_iterations=1 in the internal call
            assert last_call_kwargs["request_params"].max_iterations == 1
            # Should use the claude-3-haiku model as specified
            assert last_call_kwargs["request_params"].model == "claude-3-haiku"
            # Should use the custom maxTokens
            assert last_call_kwargs["request_params"].maxTokens == 4096

    @pytest.mark.asyncio
    async def test_anthropic_swarm_generate_multiple_iterations(
        self, mock_anthropic_swarm
    ):
        """Test AnthropicSwarm generate method with multiple iterations."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(max_iterations=3)
        mock_response1 = MagicMock()
        mock_response2 = MagicMock()
        mock_response3 = MagicMock()

        # Set up the super().generate method to return different responses for each call
        side_effects = [mock_response1, mock_response2, mock_response3]

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_anthropic.AnthropicAugmentedLLM.generate",
            AsyncMock(side_effect=side_effects),
        ) as mock_generate:
            # Call generate
            result = await mock_anthropic_swarm.generate(message, custom_params)

            # Assert the result is the final response
            assert result == mock_response3

            # Check that AnthropicAugmentedLLM.generate was called three times
            assert mock_generate.call_count == 3

            # Check the messages for each call
            first_call_kwargs = mock_generate.call_args_list[0][1]
            assert first_call_kwargs["message"] == message

            # Second and third calls should use the follow-up message
            second_call_kwargs = mock_generate.call_args_list[1][1]
            assert (
                second_call_kwargs["message"]
                == "Please resolve my original request. If it has already been resolved then end turn"
            )

            third_call_kwargs = mock_generate.call_args_list[2][1]
            assert (
                third_call_kwargs["message"]
                == "Please resolve my original request. If it has already been resolved then end turn"
            )

    @pytest.mark.asyncio
    async def test_anthropic_swarm_generate_early_termination(
        self, mock_anthropic_swarm
    ):
        """Test AnthropicSwarm generate method with early termination."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(max_iterations=3)
        mock_response = MagicMock()

        # Mock super().generate to return a response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_anthropic.AnthropicAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Set up should_continue to return False after the first iteration
            mock_anthropic_swarm.should_continue = MagicMock(side_effect=[True, False])

            # Call generate
            result = await mock_anthropic_swarm.generate(message, custom_params)

            # Assert the result is our response
            assert result == mock_response

            # Check that AnthropicAugmentedLLM.generate was called only once
            assert mock_generate.call_count == 1

    @pytest.mark.asyncio
    async def test_anthropic_swarm_generate_with_done_agent(
        self, mock_anthropic_swarm, done_agent
    ):
        """Test AnthropicSwarm generate method with a DoneAgent."""
        # Setup
        message = "Test message"
        mock_response = MagicMock()

        # Set the agent to a DoneAgent
        mock_anthropic_swarm.agent = done_agent

        # Ensure we only make one iteration
        mock_anthropic_swarm.should_continue = MagicMock(side_effect=[True, False])

        # Mock super().generate to return a response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_anthropic.AnthropicAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate
            result = await mock_anthropic_swarm.generate(message)

            # Assert the result is our response
            assert result == mock_response

            # Check that AnthropicAugmentedLLM.generate was called only once
            assert mock_generate.call_count == 1
