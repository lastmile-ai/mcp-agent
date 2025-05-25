import pytest
from unittest.mock import AsyncMock, patch

from mcp_agent.workflows.parallel.fan_in import FanIn
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestFanIn:
    """
    Tests for the FanIn class.
    """

    @pytest.fixture
    def fan_in_with_agent(self, mock_context, mock_agent, mock_llm_factory):
        """
        Creates a FanIn instance with an Agent and LLM factory.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanIn(
            aggregator_agent=mock_agent,
            llm_factory=mock_llm_factory,
            context=mock_context,
        )

    @pytest.fixture
    def fan_in_with_llm(self, mock_context, mock_llm):
        """
        Creates a FanIn instance with an AugmentedLLM.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanIn(
            aggregator_agent=mock_llm,
            context=mock_context,
        )

    # Test 1: Initialization Tests
    def test_init_with_agent_and_factory(
        self, fan_in_with_agent, mock_agent, mock_llm_factory
    ):
        """
        Tests initialization with an Agent and LLM factory.
        """
        assert fan_in_with_agent.aggregator_agent == mock_agent
        assert fan_in_with_agent.llm_factory == mock_llm_factory

    def test_init_with_llm(self, fan_in_with_llm, mock_llm):
        """
        Tests initialization with an AugmentedLLM.
        """
        assert fan_in_with_llm.aggregator_agent == mock_llm
        assert fan_in_with_llm.llm_factory is None

    def test_init_with_agent_without_factory(self, mock_context, mock_agent):
        """
        Tests initialization with an Agent but without an LLM factory,
        which should raise a ValueError.
        """
        with pytest.raises(
            ValueError, match="llm_factory is required when using an Agent"
        ):
            FanIn(aggregator_agent=mock_agent, context=mock_context)

    # Test 2: Core Method Tests
    @pytest.mark.asyncio
    async def test_generate(self, fan_in_with_llm, mock_llm):
        """
        Tests the generate method with an AugmentedLLM.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}
        expected_result = ["Response from LLM"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_llm.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )
        mock_llm.generate.return_value = expected_result

        # Call the method
        result = await fan_in_with_llm.generate(messages, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_messages.assert_called_once_with(messages)
        mock_llm.generate.assert_called_once_with(
            message="Aggregated message", request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_with_agent(
        self, fan_in_with_agent, mock_agent, mock_llm, mock_llm_factory
    ):
        """
        Tests the generate method with an Agent.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}
        expected_result = ["Response from Agent"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_agent.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )

        # Configure the return value from the generate method
        mock_llm.generate = AsyncMock()
        mock_llm.generate.return_value = expected_result

        # Configure the agent to return the llm when attach_llm is called
        mock_agent.attach_llm = AsyncMock(return_value=mock_llm)

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent

            # Call the method
            result = await fan_in_with_agent.generate(messages, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_agent.aggregate_messages.assert_called_once_with(messages)
        mock_agent.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm.generate.assert_called_once_with(
            message="Aggregated message", request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_str(self, fan_in_with_llm, mock_llm):
        """
        Tests the generate_str method with an AugmentedLLM.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}
        expected_result = "Response from LLM"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_llm.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )
        mock_llm.generate_str.return_value = expected_result

        # Call the method
        result = await fan_in_with_llm.generate_str(messages, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_messages.assert_called_once_with(messages)
        mock_llm.generate_str.assert_called_once_with(
            message="Aggregated message", request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_str_with_agent(
        self, fan_in_with_agent, mock_agent, mock_llm, mock_llm_factory
    ):
        """
        Tests the generate_str method with an Agent.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}
        expected_result = "Response from Agent"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_agent.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )

        # Configure the return value from the generate_str method
        mock_llm.generate_str = AsyncMock()
        mock_llm.generate_str.return_value = expected_result

        # Configure the agent to return the llm when attach_llm is called
        mock_agent.attach_llm = AsyncMock(return_value=mock_llm)

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent

            # Call the method
            result = await fan_in_with_agent.generate_str(messages, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_agent.aggregate_messages.assert_called_once_with(messages)
        mock_agent.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm.generate_str.assert_called_once_with(
            message="Aggregated message", request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_structured(self, fan_in_with_llm, mock_llm):
        """
        Tests the generate_structured method with an AugmentedLLM.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_llm.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )
        mock_llm.generate_structured.return_value = expected_result

        # Call the method
        result = await fan_in_with_llm.generate_structured(
            messages, TestResponseModel, request_params
        )

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_messages.assert_called_once_with(messages)
        mock_llm.generate_structured.assert_called_once_with(
            message="Aggregated message",
            response_model=TestResponseModel,
            request_params=request_params,
        )

    @pytest.mark.asyncio
    async def test_generate_structured_with_agent(
        self, fan_in_with_agent, mock_agent, mock_llm, mock_llm_factory
    ):
        """
        Tests the generate_structured method with an Agent.
        """
        # Set up test data
        messages = {"agent1": ["Hello"], "agent2": ["World"]}

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        fan_in_with_agent.aggregate_messages = AsyncMock(
            return_value="Aggregated message"
        )

        # Configure the return value from the generate_structured method
        mock_llm.generate_structured = AsyncMock()
        mock_llm.generate_structured.return_value = expected_result

        # Configure the agent to return the llm when attach_llm is called
        mock_agent.attach_llm = AsyncMock(return_value=mock_llm)

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent

            # Call the method
            result = await fan_in_with_agent.generate_structured(
                messages, TestResponseModel, request_params
            )

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_agent.aggregate_messages.assert_called_once_with(messages)
        mock_agent.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm.generate_structured.assert_called_once_with(
            message="Aggregated message",
            response_model=TestResponseModel,
            request_params=request_params,
        )

    # Test 3: Aggregation Method Tests
    @pytest.mark.asyncio
    async def test_aggregate_messages_dict_message_lists(self, fan_in_with_llm):
        """
        Tests aggregate_messages with a dictionary of agent names to message lists.
        """
        # Set up test data
        messages = {"agent1": ["Message 1", "Message 2"], "agent2": ["Message 3"]}

        # Set up mock for aggregate_agent_messages
        expected_result = "Aggregated messages"
        fan_in_with_llm.aggregate_agent_messages = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await fan_in_with_llm.aggregate_messages(messages)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_agent_messages.assert_called_once_with(messages)

    @pytest.mark.asyncio
    async def test_aggregate_messages_dict_strings(self, fan_in_with_llm):
        """
        Tests aggregate_messages with a dictionary of agent names to strings.
        """
        # Set up test data
        messages = {"agent1": "Message 1", "agent2": "Message 2"}

        # Set up mock for aggregate_agent_message_strings
        expected_result = "Aggregated message strings"
        fan_in_with_llm.aggregate_agent_message_strings = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await fan_in_with_llm.aggregate_messages(messages)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_agent_message_strings.assert_called_once_with(
            messages
        )

    @pytest.mark.asyncio
    async def test_aggregate_messages_list_message_lists(self, fan_in_with_llm):
        """
        Tests aggregate_messages with a list of message lists.
        """
        # Set up test data
        messages = [["Message 1", "Message 2"], ["Message 3"]]

        # Set up mock for aggregate_message_lists
        expected_result = "Aggregated message lists"
        fan_in_with_llm.aggregate_message_lists = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await fan_in_with_llm.aggregate_messages(messages)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_message_lists.assert_called_once_with(messages)

    @pytest.mark.asyncio
    async def test_aggregate_messages_list_strings(self, fan_in_with_llm):
        """
        Tests aggregate_messages with a list of strings.
        """
        # Set up test data
        messages = ["Message 1", "Message 2"]

        # Set up mock for aggregate_message_strings
        expected_result = "Aggregated message strings"
        fan_in_with_llm.aggregate_message_strings = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await fan_in_with_llm.aggregate_messages(messages)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        fan_in_with_llm.aggregate_message_strings.assert_called_once_with(messages)

    @pytest.mark.asyncio
    async def test_aggregate_messages_empty_dict(self, fan_in_with_llm):
        """
        Tests aggregate_messages with an empty dictionary, which should raise a ValueError.
        """
        with pytest.raises(ValueError, match="Input dictionary cannot be empty"):
            await fan_in_with_llm.aggregate_messages({})

    @pytest.mark.asyncio
    async def test_aggregate_messages_empty_list(self, fan_in_with_llm):
        """
        Tests aggregate_messages with an empty list, which should raise a ValueError.
        """
        with pytest.raises(ValueError, match="Input list cannot be empty"):
            await fan_in_with_llm.aggregate_messages([])

    @pytest.mark.asyncio
    async def test_aggregate_messages_invalid_dict_values(self, fan_in_with_llm):
        """
        Tests aggregate_messages with invalid dictionary values, which should raise a ValueError.
        """
        # Mixed types (string and list)
        with pytest.raises(
            ValueError,
            match="All dictionary values must be (lists of messages|strings)",
        ):
            await fan_in_with_llm.aggregate_messages(
                {"agent1": ["Message"], "agent2": "Message"}
            )

        # Invalid type (neither string nor list)
        with pytest.raises(
            ValueError,
            match="Dictionary values must be either lists of messages or strings",
        ):
            await fan_in_with_llm.aggregate_messages({"agent1": 123})

    @pytest.mark.asyncio
    async def test_aggregate_messages_invalid_list_items(self, fan_in_with_llm):
        """
        Tests aggregate_messages with invalid list items, which should raise a ValueError.
        """
        # Mixed types (string and list)
        with pytest.raises(
            ValueError, match="All list items must be (lists of messages|strings)"
        ):
            await fan_in_with_llm.aggregate_messages([["Message"], "Message"])

        # Invalid type (neither string nor list)
        with pytest.raises(
            ValueError, match="List items must be either lists of messages or strings"
        ):
            await fan_in_with_llm.aggregate_messages([123])

    @pytest.mark.asyncio
    async def test_aggregate_messages_invalid_input_type(self, fan_in_with_llm):
        """
        Tests aggregate_messages with an invalid input type, which should raise a ValueError.
        """
        with pytest.raises(
            ValueError,
            match="Input must be either a dictionary of agent messages or a list of messages",
        ):
            await fan_in_with_llm.aggregate_messages(123)

    # Test 4: Helper Method Tests
    @pytest.mark.asyncio
    async def test_aggregate_agent_messages(self, fan_in_with_llm):
        """
        Tests the aggregate_agent_messages helper method.
        """
        # Set up test data
        messages = {"agent1": ["Message 1", "Message 2"], "agent2": ["Message 3"]}

        # Call the method
        result = await fan_in_with_llm.aggregate_agent_messages(messages)

        # Assert the result contains expected content
        assert "Aggregated responses from multiple Agents" in result
        assert "Agent agent1" in result
        assert "Agent agent2" in result
        assert "Message 1" in result
        assert "Message 2" in result
        assert "Message 3" in result

    @pytest.mark.asyncio
    async def test_aggregate_agent_messages_empty(self, fan_in_with_llm):
        """
        Tests the aggregate_agent_messages helper method with empty input.
        """
        # Call the method with empty dict
        result = await fan_in_with_llm.aggregate_agent_messages({})

        # Assert the result is an empty string
        assert result == ""

    @pytest.mark.asyncio
    async def test_aggregate_agent_message_strings(self, fan_in_with_llm):
        """
        Tests the aggregate_agent_message_strings helper method.
        """
        # Set up test data
        messages = {"agent1": "Message 1", "agent2": "Message 2"}

        # Call the method
        result = await fan_in_with_llm.aggregate_agent_message_strings(messages)

        # Assert the result contains expected content
        assert "Aggregated responses from multiple Agents" in result
        assert "Agent agent1: Message 1" in result
        assert "Agent agent2: Message 2" in result

    @pytest.mark.asyncio
    async def test_aggregate_agent_message_strings_empty(self, fan_in_with_llm):
        """
        Tests the aggregate_agent_message_strings helper method with empty input.
        """
        # Call the method with empty dict
        result = await fan_in_with_llm.aggregate_agent_message_strings({})

        # Assert the result is an empty string
        assert result == ""

    @pytest.mark.asyncio
    async def test_aggregate_message_lists(self, fan_in_with_llm):
        """
        Tests the aggregate_message_lists helper method.
        """
        # Set up test data
        messages = [["Message 1", "Message 2"], ["Message 3"]]

        # Call the method
        result = await fan_in_with_llm.aggregate_message_lists(messages)

        # Assert the result contains expected content
        assert "Aggregated responses from multiple sources" in result
        # Inspect the actual output format to make the right assertions
        assert "Message 1" in result
        assert "Message 2" in result
        assert "Message 3" in result

    @pytest.mark.asyncio
    async def test_aggregate_message_lists_empty(self, fan_in_with_llm):
        """
        Tests the aggregate_message_lists helper method with empty input.
        """
        # Call the method with empty list
        result = await fan_in_with_llm.aggregate_message_lists([])

        # Assert the result is an empty string
        assert result == ""

    @pytest.mark.asyncio
    async def test_aggregate_message_strings(self, fan_in_with_llm):
        """
        Tests the aggregate_message_strings helper method.
        """
        # Set up test data
        messages = ["Message 1", "Message 2"]

        # Call the method
        result = await fan_in_with_llm.aggregate_message_strings(messages)

        # Assert the result contains expected content
        assert "Aggregated responses from multiple sources" in result
        assert "Source 1: Message 1" in result
        assert "Source 2: Message 2" in result

    @pytest.mark.asyncio
    async def test_aggregate_message_strings_empty(self, fan_in_with_llm):
        """
        Tests the aggregate_message_strings helper method with empty input.
        """
        # Call the method with empty list
        result = await fan_in_with_llm.aggregate_message_strings([])

        # Assert the result is an empty string
        assert result == ""
