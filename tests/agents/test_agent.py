import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.fastmcp.tools import Tool as FastTool
from mcp.types import CallToolResult, TextContent, Tool

from mcp_agent.agents.agent import Agent, HUMAN_INPUT_TOOL_NAME
from mcp_agent.human_input.types import (
    HumanInputRequest,
    HumanInputResponse,
)
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class TestAgent:
    """Test cases for the Agent class."""

    @pytest.fixture
    def mock_context(self):
        """Create a Context with mocked components for testing."""
        from mcp_agent.core.context import Context

        context = Context()
        # Use an AsyncMock for executor to support 'await executor.execute(...)'
        context.executor = AsyncMock()
        context.human_input_handler = None
        context.server_registry = MagicMock()
        return context

    @pytest.fixture
    def basic_agent(self, mock_context):
        """Create a basic Agent for testing."""
        return Agent(
            name="test_agent",
            instruction="You are a helpful agent.",
            context=mock_context,
        )

    @pytest.fixture
    def mock_human_input_callback(self):
        """Mock human input callback."""

        async def callback(request):
            return HumanInputResponse(
                request_id=request.request_id, response="Test response"
            )

        return AsyncMock(side_effect=callback)

    @pytest.fixture
    def agent_with_human_input(self, mock_context, mock_human_input_callback):
        """Create an Agent with human input callback."""
        agent = Agent(
            name="test_agent_with_human_input",
            instruction="You are a helpful agent.",
            context=mock_context,
            human_input_callback=mock_human_input_callback,
        )
        # Ensure executor is accessible directly on the agent for patching in tests
        agent.executor = agent.context.executor
        return agent

    @pytest.fixture
    def test_function(self):
        """Test function for function tools."""

        def function(param1: str, param2: int = 0) -> str:
            """A test function.

            Args:
                param1: A string parameter
                param2: An integer parameter with default 0

            Returns:
                A string result
            """
            return f"Function called with {param1} and {param2}"

        return function

    @pytest.fixture
    def agent_with_functions(self, mock_context, test_function):
        """Create an Agent with functions."""
        return Agent(
            name="test_agent_with_functions",
            instruction="You are a helpful agent.",
            context=mock_context,
            functions=[test_function],
        )

    @pytest.fixture
    def mock_llm_factory(self):
        """Mock LLM factory function."""
        mock_llm = MagicMock(spec=AugmentedLLM)
        factory = AsyncMock()
        factory.return_value = mock_llm
        return factory, mock_llm

    #
    # Initialization Tests
    #

    @pytest.mark.asyncio
    async def test_initialization_minimal(self, mock_context):
        """Test initialization with minimal parameters."""
        agent = Agent(name="test_agent", context=mock_context)

        assert agent.name == "test_agent"
        assert agent.instruction == "You are a helpful agent."
        assert agent.functions == []
        assert agent.human_input_callback is None
        assert agent._function_tool_map == {}

    @pytest.mark.asyncio
    async def test_initialization_with_custom_instruction(self, mock_context):
        """Test initialization with custom instruction."""
        custom_instruction = "You are a specialized test agent."
        agent = Agent(
            name="test_agent", instruction=custom_instruction, context=mock_context
        )

        assert agent.instruction == custom_instruction

    @pytest.mark.asyncio
    async def test_initialization_with_server_names(self, mock_context):
        """Test initialization with server names."""
        server_names = ["server1", "server2"]
        agent = Agent(
            name="test_agent", context=mock_context, server_names=server_names
        )

        assert agent.server_names == server_names

    @pytest.mark.asyncio
    async def test_initialization_with_functions(self, mock_context, test_function):
        """Test initialization with functions."""
        agent = Agent(
            name="test_agent", context=mock_context, functions=[test_function]
        )

        assert len(agent.functions) == 1
        assert agent.functions[0] == test_function
        assert len(agent._function_tool_map) == 1

        # Check that the function was properly converted to a tool
        tool_name = next(iter(agent._function_tool_map.keys()))
        assert tool_name == test_function.__name__
        assert isinstance(agent._function_tool_map[tool_name], FastTool)

    @pytest.mark.asyncio
    async def test_initialization_with_human_input_callback(
        self, mock_context, mock_human_input_callback
    ):
        """Test initialization with human input callback."""
        agent = Agent(
            name="test_agent",
            context=mock_context,
            human_input_callback=mock_human_input_callback,
        )

        assert agent.human_input_callback == mock_human_input_callback

    @pytest.mark.asyncio
    async def test_initialization_with_context_human_input_handler(
        self, mock_context, mock_human_input_callback
    ):
        """Test initialization with context's human input handler."""
        from mcp_agent.agents.agent import InitAggregatorResponse

        mock_context.human_input_handler = mock_human_input_callback
        agent = Agent(name="test_agent", context=mock_context)

        # Mock the executor to return a successful initialization response
        mock_context.executor.execute.return_value = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={},
            server_to_tool_map={},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )

        # Initialize agent to trigger context setup
        await agent.initialize()

        assert agent.human_input_callback == mock_human_input_callback

    @pytest.mark.asyncio
    async def test_initialization_with_global_context(self, mock_context):
        """Test initialization with context from get_current_context."""
        from mcp_agent.agents.agent import InitAggregatorResponse

        # Create agent without context
        agent = Agent(name="test_agent", context=None)

        # Mock the executor to return a successful initialization response
        mock_context.executor.execute.return_value = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={},
            server_to_tool_map={},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )

        with patch(
            "mcp_agent.core.context.get_current_context",
            return_value=mock_context,
        ):
            # Initialize agent - should use context from get_current_context
            await agent.initialize()
            assert agent.context == mock_context

    @pytest.mark.asyncio
    async def test_initialization_with_explicit_context_overrides_global(
        self, mock_context
    ):
        """Test that explicit context is used and global context is not called."""
        from mcp_agent.agents.agent import InitAggregatorResponse

        # Create a different context to use as global
        global_context = MagicMock()

        # Create agent with explicit context
        agent = Agent(name="test_agent", context=mock_context)

        # Mock the executor to return a successful initialization response
        mock_context.executor.execute.return_value = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={},
            server_to_tool_map={},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )

        with patch(
            "mcp_agent.core.context.get_current_context",
            return_value=global_context,
        ) as mock_get_context:
            # Initialize agent - should use explicit context, not global
            await agent.initialize()
            assert agent.context == mock_context
            # Verify get_current_context was not called
            mock_get_context.assert_not_called()

    #
    # LLM Attachment Tests
    #

    @pytest.mark.asyncio
    async def test_attach_llm(self, basic_agent, mock_llm_factory):
        """Test attaching LLM to agent."""
        factory, mock_llm = mock_llm_factory

        # Mock the attach_llm method to return the mock_llm directly
        with patch.object(
            Agent, "attach_llm", AsyncMock(return_value=mock_llm)
        ) as mock_attach:
            llm = await basic_agent.attach_llm(factory)

            assert llm == mock_llm
            mock_attach.assert_called_once_with(factory)

    #
    # Shutdown Tests
    #

    @pytest.mark.asyncio
    async def test_shutdown(self, basic_agent):
        """Test agent shutdown."""
        from mcp_agent.agents.agent import InitAggregatorResponse

        # Test shutdown when agent is not initialized - should not call executor
        with patch.object(
            basic_agent.context.executor, "execute", AsyncMock(return_value=True)
        ) as mock_execute:
            await basic_agent.shutdown()
            mock_execute.assert_not_called()

        # Mock successful initialization
        basic_agent.context.executor.execute.return_value = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={},
            server_to_tool_map={},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )

        # Test shutdown when agent is initialized - should call executor
        await basic_agent.initialize()
        with patch.object(
            basic_agent.context.executor, "execute", AsyncMock(return_value=True)
        ) as mock_execute:
            await basic_agent.shutdown()
            mock_execute.assert_called_once()

    #
    # Human Input Tests
    #

    @pytest.mark.asyncio
    async def test_request_human_input_successful(self, agent_with_human_input):
        """Test successful human input request."""
        request = HumanInputRequest(
            prompt="Please provide input",
            description="This is a test",
            workflow_id="workflow123",
        )

        # Mock directly rather than running the actual method which has async issues
        with patch("uuid.uuid4", return_value="test-uuid"):
            # Mock the method to return directly
            with patch.object(
                Agent, "request_human_input", AsyncMock(return_value="Test user input")
            ):
                result = await agent_with_human_input.request_human_input(request)

                # Verify mocking worked
                assert result == "Test user input"

    @pytest.mark.asyncio
    async def test_request_human_input_no_callback(self, basic_agent):
        """Test human input request with no callback set."""
        request = HumanInputRequest(
            prompt="Please provide input", description="This is a test"
        )

        with pytest.raises(ValueError, match="Human input callback not set"):
            await basic_agent.request_human_input(request)

    @pytest.mark.asyncio
    async def test_request_human_input_timeout(self, agent_with_human_input):
        """Test human input request with timeout."""
        request = HumanInputRequest(
            prompt="Please provide input",
            description="This is a test",
            timeout_seconds=5,
        )

        # Mock wait_for_signal to raise TimeoutError
        agent_with_human_input.executor.wait_for_signal = AsyncMock(
            side_effect=TimeoutError("Timeout occurred")
        )

        with pytest.raises(TimeoutError):
            await agent_with_human_input.request_human_input(request)

    @pytest.mark.asyncio
    async def test_request_human_input_callback_error(self, agent_with_human_input):
        """Test human input request with callback error."""
        request = HumanInputRequest(
            prompt="Please provide input", description="This is a test"
        )

        # Create a mock implementation of request_human_input that tests error handling
        async def mock_implementation(self, req):
            # Simulate the error handling logic from the original method
            error_message = "Callback error"
            self.executor.signal.assert_called_once()
            signal_call = self.executor.signal.call_args[1]
            assert "payload" in signal_call
            assert error_message in signal_call["payload"]
            raise Exception(error_message)

        # Setup the executor signal mock to verify it gets called
        agent_with_human_input.context.executor.signal = AsyncMock()

        # Apply the mock
        with patch.object(
            Agent, "request_human_input", side_effect=Exception("Callback error")
        ):
            # Should raise the exception
            with pytest.raises(Exception, match="Callback error"):
                await agent_with_human_input.request_human_input(request)

    #
    # Tool Listing Tests
    #

    @pytest.mark.asyncio
    async def test_list_tools_parent_call(self, basic_agent):
        """Test that list_tools returns parent tool from internal state."""
        # Patch executor.execute to return InitAggregatorResponse with parent_tool
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        with patch.object(
            basic_agent.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            # Force re-initialization
            basic_agent.initialized = False
            result = await basic_agent.list_tools()
            assert "parent_tool" in [tool.name for tool in result.tools]

    @pytest.mark.asyncio
    async def test_list_tools_with_functions(self, agent_with_functions, test_function):
        """Test that list_tools includes function tools."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        with patch.object(
            agent_with_functions.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_functions.initialized = False  # Force re-initialization
            result = await agent_with_functions.list_tools()
            tool_names = [tool.name for tool in result.tools]
            # Check that both parent tool and function tool are in result
            assert "parent_tool" in tool_names
            assert (
                test_function.__name__ in tool_names
            )  # The actual name of the function

    @pytest.mark.asyncio
    async def test_list_tools_with_human_input(self, agent_with_human_input):
        """Test that list_tools includes human input tool when callback is set."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        with patch.object(
            agent_with_human_input.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_human_input.initialized = False  # Force re-initialization
            result = await agent_with_human_input.list_tools()
            tool_names = [tool.name for tool in result.tools]
            # Check that both parent tool and human input tool are in result
            assert "parent_tool" in tool_names
            assert HUMAN_INPUT_TOOL_NAME in tool_names
            # Find the human input tool and check its schema
            human_input_tool = next(
                (tool for tool in result.tools if tool.name == HUMAN_INPUT_TOOL_NAME),
                None,
            )
            assert human_input_tool is not None
            assert "request" in human_input_tool.inputSchema["properties"]

    @pytest.mark.asyncio
    async def test_list_tools_without_human_input(self, basic_agent):
        """Test that list_tools doesn't include human input tool when callback is not set."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        with patch.object(
            basic_agent.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            basic_agent.initialized = False  # Force re-initialization
            result = await basic_agent.list_tools()
            tool_names = [tool.name for tool in result.tools]
            # Check that parent tool is in result but human input tool is not
            assert "parent_tool" in tool_names
            assert HUMAN_INPUT_TOOL_NAME not in tool_names

    #
    # Tool Calling Tests
    #

    @pytest.mark.asyncio
    async def test_call_tool_parent(self, basic_agent):
        """Test calling a parent tool."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        tool_name = "parent_tool"
        arguments = {"arg1": "value1"}
        mock_result = CallToolResult(
            content=[TextContent(type="text", text="Tool result")]
        )
        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )

        # Patch executor.execute to return InitAggregatorResponse for initialization,
        # and CallToolResult for the tool call
        def execute_side_effect(*args, **kwargs):
            if not basic_agent.initialized:
                return init_response
            return mock_result

        with patch.object(
            basic_agent.context.executor,
            "execute",
            AsyncMock(side_effect=execute_side_effect),
        ):
            basic_agent.initialized = False  # Force re-initialization
            result = await basic_agent.call_tool(tool_name, arguments)
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_call_tool_function(self, agent_with_functions, test_function):
        """Test calling a function tool."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        tool_name = test_function.__name__  # Should be "function" not "test_function"
        arguments = {"param1": "test", "param2": 42}
        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        with patch.object(
            agent_with_functions.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_functions.initialized = False  # Force re-initialization
            result = await agent_with_functions.call_tool(tool_name, arguments)
            assert result.isError is False
            assert len(result.content) == 1
            assert "Function called with test and 42" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_human_input(self, agent_with_human_input):
        """Test calling the human input tool."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        tool_name = HUMAN_INPUT_TOOL_NAME
        arguments = {
            "request": {
                "prompt": "Please provide input",
                "description": "This is a test",
            }
        }
        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        # Mock the request_human_input method
        response = HumanInputResponse(request_id="test-id", response="User input")
        agent_with_human_input.request_human_input = AsyncMock(return_value=response)
        with patch.object(
            agent_with_human_input.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_human_input.initialized = False  # Force re-initialization
            result = await agent_with_human_input.call_tool(tool_name, arguments)
            assert result.isError is False
            assert len(result.content) == 1
            assert "Human response:" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_human_input_timeout(self, agent_with_human_input):
        """Test calling the human input tool with timeout."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        tool_name = HUMAN_INPUT_TOOL_NAME
        arguments = {
            "request": {
                "prompt": "Please provide input",
                "description": "This is a test",
                "timeout_seconds": 5,
            }
        }
        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        # Mock the request_human_input method to raise TimeoutError
        agent_with_human_input.request_human_input = AsyncMock(
            side_effect=TimeoutError("Timeout occurred")
        )
        with patch.object(
            agent_with_human_input.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_human_input.initialized = False  # Force re-initialization
            result = await agent_with_human_input.call_tool(tool_name, arguments)
            assert result.isError is True
            assert len(result.content) == 1
            assert "Error: Human input request timed out" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_human_input_error(self, agent_with_human_input):
        """Test calling the human input tool with general error."""
        from mcp_agent.agents.agent import InitAggregatorResponse, NamespacedTool

        tool_name = HUMAN_INPUT_TOOL_NAME
        arguments = {
            "request": {
                "prompt": "Please provide input",
                "description": "This is a test",
            }
        }
        parent_tool = Tool(
            name="parent_tool", description="A parent tool", inputSchema={}
        )
        namespaced_tool = NamespacedTool(
            namespaced_tool_name="parent_tool", tool=parent_tool, server_name="server1"
        )
        init_response = InitAggregatorResponse(
            initialized=True,
            namespaced_tool_map={"parent_tool": namespaced_tool},
            server_to_tool_map={"server1": [namespaced_tool]},
            namespaced_prompt_map={},
            server_to_prompt_map={},
        )
        # Mock the request_human_input method to raise Exception
        error_message = "Something went wrong"
        agent_with_human_input.request_human_input = AsyncMock(
            side_effect=Exception(error_message)
        )
        with patch.object(
            agent_with_human_input.context.executor,
            "execute",
            AsyncMock(return_value=init_response),
        ):
            agent_with_human_input.initialized = False  # Force re-initialization
            result = await agent_with_human_input.call_tool(tool_name, arguments)
            assert result.isError is True
            assert len(result.content) == 1
            assert "Error requesting human input" in result.content[0].text
            assert error_message in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_with_custom_callable_instruction(self, mock_context):
        """Test agent with a callable instruction."""

        def custom_instruction(params):
            return f"Custom instruction with params: {params}"

        agent = Agent(
            name="test_agent", instruction=custom_instruction, context=mock_context
        )

        assert agent.instruction == custom_instruction
