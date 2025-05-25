import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.parallel.fan_out import FanOut
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestFanOut:
    """
    Tests for the FanOut class.
    """

    @pytest.fixture
    def mock_function(self):
        """
        Returns a mock function for testing.
        """
        fn = MagicMock()
        fn.__name__ = "mock_function"
        return fn

    @pytest.fixture
    def mock_agent_with_name(self, mock_agent):
        """
        Returns a mock Agent instance with a name attribute for testing.
        """
        mock_agent.name = "test_agent"
        return mock_agent

    @pytest.fixture
    def mock_llm_with_name(self, mock_llm):
        """
        Returns a mock AugmentedLLM instance with a name attribute for testing.
        """
        mock_llm.name = "test_llm"
        return mock_llm

    @pytest.fixture
    def fan_out_with_agents(self, mock_context, mock_agent_with_name, mock_llm_factory):
        """
        Creates a FanOut instance with agents and an LLM factory.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanOut(
            agents=[mock_agent_with_name],
            llm_factory=mock_llm_factory,
            context=mock_context,
        )

    @pytest.fixture
    def fan_out_with_llms(self, mock_context, mock_llm_with_name):
        """
        Creates a FanOut instance with AugmentedLLMs.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanOut(
            agents=[mock_llm_with_name],
            context=mock_context,
        )

    @pytest.fixture
    def fan_out_with_functions(self, mock_context, mock_function):
        """
        Creates a FanOut instance with functions.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanOut(
            functions=[mock_function],
            context=mock_context,
        )

    @pytest.fixture
    def fan_out_with_mixed(
        self,
        mock_context,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_function,
        mock_llm_factory,
    ):
        """
        Creates a FanOut instance with a mix of agents, LLMs, and functions.
        """
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        return FanOut(
            agents=[mock_agent_with_name, mock_llm_with_name],
            functions=[mock_function],
            llm_factory=mock_llm_factory,
            context=mock_context,
        )

    # Test 1: Initialization Tests
    def test_init_with_agents_and_factory(
        self, fan_out_with_agents, mock_agent_with_name, mock_llm_factory, mock_context
    ):
        """
        Tests initialization with agents and an LLM factory.
        """
        fan_out = fan_out_with_agents
        assert fan_out.agents == [mock_agent_with_name]
        assert fan_out.llm_factory == mock_llm_factory
        assert fan_out.context == mock_context
        assert fan_out.executor == mock_context.executor
        assert fan_out.functions == []

    def test_init_with_llms(self, fan_out_with_llms, mock_llm_with_name, mock_context):
        """
        Tests initialization with AugmentedLLMs.
        """
        fan_out = fan_out_with_llms
        assert fan_out.agents == [mock_llm_with_name]
        assert fan_out.llm_factory is None
        assert fan_out.context == mock_context
        assert fan_out.functions == []

    def test_init_with_functions(
        self, fan_out_with_functions, mock_function, mock_context
    ):
        """
        Tests initialization with functions.
        """
        fan_out = fan_out_with_functions
        assert fan_out.agents == []
        assert fan_out.functions == [mock_function]
        assert fan_out.context == mock_context

    def test_init_with_mixed(
        self,
        fan_out_with_mixed,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_function,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests initialization with a mix of agents, LLMs, and functions.
        """
        fan_out = fan_out_with_mixed
        assert fan_out.agents == [mock_agent_with_name, mock_llm_with_name]
        assert fan_out.functions == [mock_function]
        assert fan_out.llm_factory == mock_llm_factory
        assert fan_out.context == mock_context

    def test_init_with_no_agents_or_functions(self, mock_context):
        """
        Tests initialization with no agents or functions, which should raise a ValueError.
        """
        with pytest.raises(
            ValueError,
            match="At least one agent or function must be provided for fan-out to work",
        ):
            FanOut(context=mock_context)

    def test_init_with_agent_without_factory(self, mock_context, mock_agent_with_name):
        """
        Tests initialization with an agent but without an LLM factory,
        which should raise a ValueError.
        """
        with pytest.raises(
            ValueError, match="llm_factory is required when using an Agent"
        ):
            FanOut(agents=[mock_agent_with_name], context=mock_context)

    # Test 2: Core Method Tests
    @pytest.mark.asyncio
    async def test_generate_with_llms(
        self, fan_out_with_llms, mock_llm_with_name, mock_context
    ):
        """
        Tests the generate method with AugmentedLLMs.
        """
        # Set up test data
        message = "Test message"
        expected_result = ["Response from LLM"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_llms.generate(message, request_params)

        # Assert the result
        assert result == {mock_llm_with_name.name: expected_result}

        # Verify method calls
        mock_llm_with_name.generate.assert_called_once_with(
            message=message, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_with_agents(
        self,
        fan_out_with_agents,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests the generate method with Agents.
        """
        # Set up test data
        message = "Test message"
        expected_result = ["Response from Agent"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate.return_value = expected_result
        mock_agent_with_name.attach_llm = AsyncMock(return_value=mock_llm_with_name)
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent_with_name

            # Call the method
            result = await fan_out_with_agents.generate(message, request_params)

        # Assert the result
        assert result == {mock_agent_with_name.name: expected_result}

        # Verify method calls
        mock_agent_with_name.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm_with_name.generate.assert_called_once_with(
            message=message, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_with_functions(
        self, fan_out_with_functions, mock_function, mock_context
    ):
        """
        Tests the generate method with functions.
        """
        # Set up test data
        message = "Test message"
        expected_result = ["Response from function"]

        # Set up mocks
        # We don't call functions directly in the fan-out implementation,
        # they are wrapped in functools.partial and executed by the executor
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_functions.generate(message)

        # Assert the result
        assert result == {"mock_function": expected_result}

        # In the implementation, we create a bound function with functools.partial
        # and the executor handles its execution, so we don't verify a direct call here
        mock_context.executor.execute_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_mixed(
        self,
        fan_out_with_mixed,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_function,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests the generate method with a mix of agents, LLMs, and functions.
        """
        # Set up test data
        message = "Test message"
        agent_result = ["Response from Agent"]
        llm_result = ["Response from LLM"]
        function_result = ["Response from function"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate.return_value = llm_result
        mock_agent_with_name.attach_llm = AsyncMock(return_value=mock_llm_with_name)
        # No need to mock function return value as it's executed by the executor

        # Set up executor to return multiple results
        mock_context.executor.execute_many = AsyncMock(
            return_value=[agent_result, llm_result, function_result]
        )

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent_with_name

            # Call the method
            result = await fan_out_with_mixed.generate(message, request_params)

        # Assert the result
        assert result == {
            mock_agent_with_name.name: agent_result,
            mock_llm_with_name.name: llm_result,
            "mock_function": function_result,
        }

        # Verify method calls
        mock_agent_with_name.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm_with_name.generate.assert_any_call(
            message=message, request_params=request_params
        )
        mock_context.executor.execute_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_str_with_llms(
        self, fan_out_with_llms, mock_llm_with_name, mock_context
    ):
        """
        Tests the generate_str method with AugmentedLLMs.
        """
        # Set up test data
        message = "Test message"
        expected_result = "Response from LLM"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate_str.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_llms.generate_str(message, request_params)

        # Assert the result
        assert result == {mock_llm_with_name.name: expected_result}

        # Verify method calls
        mock_llm_with_name.generate_str.assert_called_once_with(
            message=message, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_str_with_agents(
        self,
        fan_out_with_agents,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests the generate_str method with Agents.
        """
        # Set up test data
        message = "Test message"
        expected_result = "Response from Agent"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate_str.return_value = expected_result
        mock_agent_with_name.attach_llm = AsyncMock(return_value=mock_llm_with_name)
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent_with_name

            # Call the method
            result = await fan_out_with_agents.generate_str(message, request_params)

        # Assert the result
        assert result == {mock_agent_with_name.name: expected_result}

        # Verify method calls
        mock_agent_with_name.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm_with_name.generate_str.assert_called_once_with(
            message=message, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_str_with_functions(
        self, fan_out_with_functions, mock_function, mock_context
    ):
        """
        Tests the generate_str method with functions.
        """
        # Set up test data
        message = "Test message"
        expected_result = "Response from function"

        # Set up mocks
        mock_function.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_functions.generate_str(message)

        # Assert the result
        assert result == {"mock_function": expected_result}

        # Verify method calls
        mock_context.executor.execute_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_structured_with_llms(
        self, fan_out_with_llms, mock_llm_with_name, mock_context
    ):
        """
        Tests the generate_structured method with AugmentedLLMs.
        """
        # Set up test data
        message = "Test message"

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate_structured.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_llms.generate_structured(
            message, TestResponseModel, request_params
        )

        # Assert the result
        assert result == {mock_llm_with_name.name: expected_result}

        # Verify method calls
        mock_llm_with_name.generate_structured.assert_called_once_with(
            message=message,
            response_model=TestResponseModel,
            request_params=request_params,
        )

    @pytest.mark.asyncio
    async def test_generate_structured_with_agents(
        self,
        fan_out_with_agents,
        mock_agent_with_name,
        mock_llm_with_name,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests the generate_structured method with Agents.
        """
        # Set up test data
        message = "Test message"

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        mock_llm_with_name.generate_structured.return_value = expected_result
        mock_agent_with_name.attach_llm = AsyncMock(return_value=mock_llm_with_name)
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Create a patch for contextlib.AsyncExitStack
        with patch("contextlib.AsyncExitStack") as MockAsyncExitStack:
            # Configure the mock stack
            mock_stack = AsyncMock()
            MockAsyncExitStack.return_value = mock_stack
            mock_stack.__aenter__.return_value = mock_stack
            mock_stack.enter_async_context.return_value = mock_agent_with_name

            # Call the method
            result = await fan_out_with_agents.generate_structured(
                message, TestResponseModel, request_params
            )

        # Assert the result
        assert result == {mock_agent_with_name.name: expected_result}

        # Verify method calls
        mock_agent_with_name.attach_llm.assert_called_once_with(mock_llm_factory)
        mock_llm_with_name.generate_structured.assert_called_once_with(
            message=message,
            response_model=TestResponseModel,
            request_params=request_params,
        )

    @pytest.mark.asyncio
    async def test_generate_structured_with_functions(
        self, fan_out_with_functions, mock_function, mock_context
    ):
        """
        Tests the generate_structured method with functions.
        """
        # Set up test data
        message = "Test message"

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()

        # Set up mocks
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_functions.generate_structured(
            message, TestResponseModel
        )

        # Assert the result
        assert result == {"mock_function": expected_result}

        # In the implementation, we create a bound function with functools.partial
        # and the executor handles its execution, so we don't verify a direct call here
        mock_context.executor.execute_many.assert_called_once()

    # Test 3: Edge Case Tests
    @pytest.mark.asyncio
    async def test_generate_with_empty_message(
        self, fan_out_with_llms, mock_llm_with_name, mock_context
    ):
        """
        Tests the generate method with an empty message.
        """
        # Set up test data
        message = ""
        expected_result = ["Response for empty message"]

        # Set up mocks
        mock_llm_with_name.generate.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_llms.generate(message)

        # Assert the result
        assert result == {mock_llm_with_name.name: expected_result}

        # Verify method calls
        mock_llm_with_name.generate.assert_called_once_with(
            message=message, request_params=None
        )

    @pytest.mark.asyncio
    async def test_generate_with_list_message(
        self, fan_out_with_llms, mock_llm_with_name, mock_context
    ):
        """
        Tests the generate method with a list message.
        """
        # Set up test data
        message = ["Message 1", "Message 2"]
        expected_result = ["Response for list message"]

        # Set up mocks
        mock_llm_with_name.generate.return_value = expected_result
        mock_context.executor.execute_many = AsyncMock(return_value=[expected_result])

        # Call the method
        result = await fan_out_with_llms.generate(message)

        # Assert the result
        assert result == {mock_llm_with_name.name: expected_result}

        # Verify method calls
        mock_llm_with_name.generate.assert_called_once_with(
            message=message, request_params=None
        )
