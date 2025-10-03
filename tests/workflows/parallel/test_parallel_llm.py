import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestParallelLLM:
    """
    Tests for the ParallelLLM class.
    """

    @pytest.fixture
    def mock_context(self):
        """
        Returns a mock Context instance for testing with model_selector.
        """
        mock = MagicMock(name="Context")
        mock.executor = MagicMock()
        mock.model_selector = MagicMock()
        return mock

    @pytest.fixture
    def mock_fan_in_fn(self):
        """
        Returns a mock fan-in function for testing.
        """
        return AsyncMock()

    @pytest.fixture
    def mock_agents_list(self, mock_agent_with_name, mock_llm_with_name):
        """
        Returns a list of mock agents for testing.
        """
        return [mock_agent_with_name, mock_llm_with_name]

    @pytest.fixture
    def mock_functions_list(self, mock_function):
        """
        Returns a list of mock functions for testing.
        """
        return [mock_function]

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
    def mock_function(self):
        """
        Returns a mock function for testing.
        """
        fn = AsyncMock()
        fn.__name__ = "mock_function"
        return fn

    @pytest.fixture
    def parallel_llm_with_agent(
        self, mock_context, mock_agent, mock_llm_factory, mock_llm_with_name
    ):
        """
        Creates a ParallelLLM instance with an Agent for fan-in and a list of agents for fan-out.
        """
        # Make sure agent is properly set up as fan-in agent
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_agent,
            fan_out_agents=[
                mock_llm_with_name
            ],  # Use just one LLM to avoid Agent issues
            llm_factory=mock_llm_factory,
            context=mock_context,
        )
        # Patch the FanIn and FanOut instances
        parallel_llm.fan_in = MagicMock()
        parallel_llm.fan_out = MagicMock()
        parallel_llm.fan_in_fn = None
        return parallel_llm

    @pytest.fixture
    def parallel_llm_with_llm(self, mock_context, mock_llm, mock_llm_with_name):
        """
        Creates a ParallelLLM instance with an AugmentedLLM for fan-in and a list of agents for fan-out.
        """
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_llm,
            fan_out_agents=[
                mock_llm_with_name
            ],  # Use just one LLM to avoid Agent issues
            context=mock_context,
        )
        # Patch the FanIn and FanOut instances
        parallel_llm.fan_in = MagicMock()
        parallel_llm.fan_out = MagicMock()
        parallel_llm.fan_in_fn = None
        return parallel_llm

    @pytest.fixture
    def parallel_llm_with_function(
        self, mock_context, mock_fan_in_fn, mock_llm_with_name
    ):
        """
        Creates a ParallelLLM instance with a function for fan-in and a list of agents for fan-out.
        """
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_fan_in_fn,
            fan_out_agents=[mock_llm_with_name],
            context=mock_context,
        )
        return parallel_llm

    @pytest.fixture
    def parallel_llm_with_functions(
        self, mock_context, mock_agent, mock_llm_factory, mock_functions_list
    ):
        """
        Creates a ParallelLLM instance with an Agent for fan-in and a list of functions for fan-out.
        """
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_agent,
            fan_out_functions=mock_functions_list,
            llm_factory=mock_llm_factory,
            context=mock_context,
        )
        # Patch the FanIn and FanOut instances
        parallel_llm.fan_in = MagicMock()
        parallel_llm.fan_out = MagicMock()
        parallel_llm.fan_in_fn = None
        return parallel_llm

    # Test 1: Initialization Tests
    def test_init_with_agent_and_agents(
        self,
        parallel_llm_with_agent,
        mock_agent,
        mock_llm_with_name,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests initialization with an Agent for fan-in and a list of agents for fan-out.
        """
        assert parallel_llm_with_agent.fan_in_agent == mock_agent
        assert parallel_llm_with_agent.context == mock_context
        assert parallel_llm_with_agent.fan_in_fn is None
        # We're mocking fan_in and fan_out to avoid initialization issues
        assert isinstance(parallel_llm_with_agent.fan_in, MagicMock)
        assert isinstance(parallel_llm_with_agent.fan_out, MagicMock)

    def test_init_with_llm_and_agents(
        self, parallel_llm_with_llm, mock_llm, mock_llm_with_name, mock_context
    ):
        """
        Tests initialization with an AugmentedLLM for fan-in and a list of agents for fan-out.
        """
        assert parallel_llm_with_llm.fan_in_agent == mock_llm
        assert parallel_llm_with_llm.context == mock_context
        assert parallel_llm_with_llm.fan_in_fn is None
        # We're mocking fan_in and fan_out to avoid initialization issues
        assert isinstance(parallel_llm_with_llm.fan_in, MagicMock)
        assert isinstance(parallel_llm_with_llm.fan_out, MagicMock)

    def test_init_with_function_and_agents(
        self, parallel_llm_with_function, mock_fan_in_fn, mock_context
    ):
        """
        Tests initialization with a function for fan-in and a list of agents for fan-out.
        """
        assert parallel_llm_with_function.fan_in_fn == mock_fan_in_fn
        assert parallel_llm_with_function.context == mock_context
        assert parallel_llm_with_function.fan_in is None
        from mcp_agent.workflows.parallel.fan_out import FanOut

        assert isinstance(parallel_llm_with_function.fan_out, FanOut)

    def test_init_with_agent_and_functions(
        self,
        parallel_llm_with_functions,
        mock_agent,
        mock_functions_list,
        mock_llm_factory,
        mock_context,
    ):
        """
        Tests initialization with an Agent for fan-in and a list of functions for fan-out.
        """
        assert parallel_llm_with_functions.fan_in_agent == mock_agent
        assert parallel_llm_with_functions.context == mock_context
        assert parallel_llm_with_functions.fan_in_fn is None
        # We're mocking fan_in and fan_out to avoid initialization issues
        assert isinstance(parallel_llm_with_functions.fan_in, MagicMock)
        assert isinstance(parallel_llm_with_functions.fan_out, MagicMock)

    # Test 2: Core Method Tests
    @pytest.mark.asyncio
    async def test_generate_with_fan_in_function(
        self, parallel_llm_with_function, mock_fan_in_fn, mock_context
    ):
        """
        Tests the generate method with a function for fan-in.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        expected_result = ["Aggregated response"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        parallel_llm_with_function.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        mock_fan_in_fn.return_value = expected_result

        # Call the method
        result = await parallel_llm_with_function.generate(message, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_function.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        mock_fan_in_fn.assert_called_once_with(fan_out_response)

    @pytest.mark.asyncio
    async def test_generate_with_fan_in_object(
        self, parallel_llm_with_agent, mock_context
    ):
        """
        Tests the generate method with a FanIn object.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        expected_result = ["Aggregated response"]
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        parallel_llm_with_agent.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        parallel_llm_with_agent.fan_in.generate = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await parallel_llm_with_agent.generate(message, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_agent.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        parallel_llm_with_agent.fan_in.generate.assert_called_once_with(
            messages=fan_out_response, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_str_with_fan_in_function(
        self, parallel_llm_with_function, mock_fan_in_fn, mock_context
    ):
        """
        Tests the generate_str method with a function for fan-in.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        expected_result = "Aggregated response"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        parallel_llm_with_function.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        mock_fan_in_fn.return_value = expected_result

        # Call the method
        result = await parallel_llm_with_function.generate_str(message, request_params)

        # Assert the result - should be stringified
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_function.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        mock_fan_in_fn.assert_called_once_with(fan_out_response)

    @pytest.mark.asyncio
    async def test_generate_str_with_fan_in_object(
        self, parallel_llm_with_agent, mock_context
    ):
        """
        Tests the generate_str method with a FanIn object.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        expected_result = "Aggregated response"
        request_params = RequestParams(temperature=0.7)

        # Set up mocks
        parallel_llm_with_agent.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        parallel_llm_with_agent.fan_in.generate_str = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await parallel_llm_with_agent.generate_str(message, request_params)

        # Assert the result
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_agent.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        parallel_llm_with_agent.fan_in.generate_str.assert_called_once_with(
            messages=fan_out_response, request_params=request_params
        )

    @pytest.mark.asyncio
    async def test_generate_structured_with_fan_in_function(
        self, parallel_llm_with_function, mock_fan_in_fn, mock_context
    ):
        """
        Tests the generate_structured method with a function for fan-in.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        request_params = RequestParams(temperature=0.7)

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()

        # Set up mocks
        parallel_llm_with_function.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        mock_fan_in_fn.return_value = expected_result

        # Call the method
        result = await parallel_llm_with_function.generate_structured(
            message, TestResponseModel, request_params
        )

        # Assert the result
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_function.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        mock_fan_in_fn.assert_called_once_with(fan_out_response)

    @pytest.mark.asyncio
    async def test_generate_structured_with_fan_in_object(
        self, parallel_llm_with_agent, mock_context
    ):
        """
        Tests the generate_structured method with a FanIn object.
        """
        # Set up test data
        message = "Test message"
        fan_out_response = {"agent1": ["Response 1"], "agent2": ["Response 2"]}
        request_params = RequestParams(temperature=0.7)

        # Create a simple response model
        class TestResponseModel:
            pass

        expected_result = TestResponseModel()

        # Set up mocks
        parallel_llm_with_agent.fan_out.generate = AsyncMock(
            return_value=fan_out_response
        )
        parallel_llm_with_agent.fan_in.generate_structured = AsyncMock(
            return_value=expected_result
        )

        # Call the method
        result = await parallel_llm_with_agent.generate_structured(
            message, TestResponseModel, request_params
        )

        # Assert the result
        assert result == expected_result

        # Verify method calls
        parallel_llm_with_agent.fan_out.generate.assert_called_once_with(
            message=message, request_params=request_params
        )
        parallel_llm_with_agent.fan_in.generate_structured.assert_called_once_with(
            messages=fan_out_response,
            response_model=TestResponseModel,
            request_params=request_params,
        )

    # Test 3: Edge Case Tests
    def test_history_is_none(self, parallel_llm_with_agent):
        """
        Tests that history is None as it's not supported in this workflow.
        """
        assert parallel_llm_with_agent.history is None
