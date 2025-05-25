import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.swarm.swarm_openai import OpenAISwarm
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestOpenAISwarm:
    """Tests for the OpenAISwarm class."""

    @pytest.fixture
    def mock_openai_swarm(self, mock_swarm_agent):
        """Create a mock OpenAISwarm instance."""
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Mock the should_continue method
        swarm.should_continue = MagicMock(return_value=True)

        # Mock the logger
        swarm.logger = MagicMock()

        return swarm

    @pytest.mark.asyncio
    async def test_openai_swarm_initialization(self, mock_swarm_agent):
        """Test OpenAISwarm initialization."""
        # Create an OpenAISwarm instance
        context_variables = {"var1": "value1", "var2": "value2"}
        swarm = OpenAISwarm(agent=mock_swarm_agent, context_variables=context_variables)

        # Assert swarm properties
        assert swarm.agent == mock_swarm_agent
        assert swarm.context_variables == context_variables
        assert swarm.instruction == mock_swarm_agent.instruction

    @pytest.mark.asyncio
    async def test_openai_swarm_generate_with_default_params(self, mock_openai_swarm):
        """Test OpenAISwarm generate method with default parameters."""
        # Setup
        message = "Test message"
        mock_response = MagicMock()

        # Ensure we only make one iteration
        mock_openai_swarm.should_continue = MagicMock(side_effect=[True, False])

        # Mock the parent generate method to return our mock response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_openai.OpenAIAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate with default parameters
            result = await mock_openai_swarm.generate(message)

            # Assert the result is our mock response
            assert result == mock_response

            # Check that the patched generate was called with the right parameters
            last_call_kwargs = mock_generate.call_args_list[-1][1]
            # Should only iterate once since we forced should_continue to return False
            assert last_call_kwargs["request_params"].max_iterations == 1
            # Should use the original message since we're only making one call
            assert last_call_kwargs["message"] == message
            # Should use the gpt-4o model by default
            assert last_call_kwargs["request_params"].model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_openai_swarm_generate_with_custom_params(self, mock_openai_swarm):
        """Test OpenAISwarm generate method with custom parameters."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(
            model="gpt-4-turbo", maxTokens=4096, max_iterations=3
        )
        mock_response = MagicMock()

        # Mock the parent generate method to return our mock response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_openai.OpenAIAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate with custom parameters
            result = await mock_openai_swarm.generate(message, custom_params)

            # Assert the result is our mock response
            assert result == mock_response

            # Check that the patched generate was called with the right parameters
            last_call_kwargs = mock_generate.call_args_list[-1][1]
            # Should only iterate once since max_iterations=1 in the internal call
            assert last_call_kwargs["request_params"].max_iterations == 1
            # Should use the gpt-4-turbo model as specified
            assert last_call_kwargs["request_params"].model == "gpt-4-turbo"
            # Should use the custom maxTokens
            assert last_call_kwargs["request_params"].maxTokens == 4096

    @pytest.mark.asyncio
    async def test_openai_swarm_generate_multiple_iterations(self, mock_openai_swarm):
        """Test OpenAISwarm generate method with multiple iterations."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(max_iterations=3)
        mock_response1 = MagicMock()
        mock_response2 = MagicMock()
        mock_response3 = MagicMock()

        # Set up the super().generate method to return different responses for each call
        side_effects = [mock_response1, mock_response2, mock_response3]

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_openai.OpenAIAugmentedLLM.generate",
            AsyncMock(side_effect=side_effects),
        ) as mock_generate:
            # Call generate
            result = await mock_openai_swarm.generate(message, custom_params)

            # Assert the result is the final response
            assert result == mock_response3

            # Check that the patched generate was called three times
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
    async def test_openai_swarm_generate_early_termination(self, mock_openai_swarm):
        """Test OpenAISwarm generate method with early termination."""
        # Setup
        message = "Test message"
        custom_params = RequestParams(max_iterations=3)
        mock_response = MagicMock()

        # Mock the parent generate method to return a response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_openai.OpenAIAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Set up should_continue to return False after the first iteration
            mock_openai_swarm.should_continue = MagicMock(side_effect=[True, False])

            # Call generate
            result = await mock_openai_swarm.generate(message, custom_params)

            # Assert the result is our response
            assert result == mock_response

            # Check that the patched generate was called only once
            assert mock_generate.call_count == 1

    @pytest.mark.asyncio
    async def test_openai_swarm_generate_with_done_agent(
        self, mock_openai_swarm, done_agent
    ):
        """Test OpenAISwarm generate method with a DoneAgent."""
        # Setup
        message = "Test message"
        mock_response = MagicMock()

        # Set the agent to a DoneAgent
        mock_openai_swarm.agent = done_agent

        # Ensure we only make one iteration
        mock_openai_swarm.should_continue = MagicMock(side_effect=[True, False])

        # Mock the parent generate method to return a response
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_openai.OpenAIAugmentedLLM.generate",
            AsyncMock(return_value=mock_response),
        ) as mock_generate:
            # Call generate
            result = await mock_openai_swarm.generate(message)

            # Assert the result is our response
            assert result == mock_response

            # Check that the patched generate was called only once
            assert mock_generate.call_count == 1
