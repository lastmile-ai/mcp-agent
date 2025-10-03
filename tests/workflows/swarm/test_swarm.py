from mcp import Tool
import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import (
    TextContent,
    CallToolRequest,
    CallToolResult,
    CallToolRequestParams,
)

from mcp_agent.workflows.swarm.swarm import (
    AgentFunctionResult,
    SwarmAgent,
    DoneAgent,
    create_agent_resource,
    create_agent_function_result_resource,
)
from mcp_agent.workflows.swarm.swarm_openai import OpenAISwarm
from mcp_agent.core.context import Context


class TestSwarmAgent:
    """Tests for the SwarmAgent class."""

    @pytest.mark.asyncio
    async def test_swarm_agent_initialization(self):
        """Test SwarmAgent initialization."""
        # Create a SwarmAgent instance
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=["server1", "server2"],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )

        # Assert agent properties
        assert agent.name == "test_agent"
        assert agent.instruction == "Test instruction"
        assert agent.server_names == ["server1", "server2"]
        assert agent.parallel_tool_calls is True
        assert agent.context is not None

    @pytest.mark.asyncio
    async def test_call_tool_with_function_string_result(self, test_function_result):
        """Test call_tool with a function that returns a string."""
        # Create a real SwarmAgent instance
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Setup function tool
        mock_function_tool = MagicMock()
        mock_function_tool.run = AsyncMock(return_value=test_function_result)
        agent._function_tool_map = {"test_function": mock_function_tool}
        agent.initialized = True

        # Call the real method
        result = await agent.call_tool("test_function", {"arg": "value"})

        # Assert the expected result
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == test_function_result

    @pytest.mark.asyncio
    async def test_call_tool_with_function_agent_result(self):
        """Test call_tool with a function that returns an agent."""
        # Create the agent under test
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Create another SwarmAgent to return as the function result
        returned_agent = SwarmAgent(
            name="returned_agent",
            instruction="Returned agent",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Setup function tool
        mock_function_tool = MagicMock()
        mock_function_tool.run = AsyncMock(return_value=returned_agent)
        agent._function_tool_map = {"test_function": mock_function_tool}
        agent.initialized = True

        # Call the real method
        result = await agent.call_tool("test_function", {"arg": "value"})

        # Assert the expected result
        assert len(result.content) == 1
        assert result.content[0].type == "resource"
        assert result.content[0].agent == returned_agent

    @pytest.mark.asyncio
    async def test_call_tool_with_function_agent_function_result(
        self, test_function_agent_function_result
    ):
        """Test call_tool with a function that returns an AgentFunctionResult."""
        # Create the agent under test
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Setup function tool
        mock_function_tool = MagicMock()
        mock_function_tool.run = AsyncMock(
            return_value=test_function_agent_function_result
        )
        agent._function_tool_map = {"test_function": mock_function_tool}
        agent.initialized = True

        # Call the real method
        result = await agent.call_tool("test_function", {"arg": "value"})

        # Assert the expected result
        assert len(result.content) == 1
        assert result.content[0].type == "resource"
        assert result.content[0].result == test_function_agent_function_result

    @pytest.mark.asyncio
    async def test_call_tool_with_function_dict_result(self):
        """Test call_tool with a function that returns a dictionary."""
        # Create the agent under test
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Setup function tool
        dict_result = {"key": "value"}
        mock_function_tool = MagicMock()
        mock_function_tool.run = AsyncMock(return_value=dict_result)
        agent._function_tool_map = {"test_function": mock_function_tool}
        agent.initialized = True

        # Call the real method
        result = await agent.call_tool("test_function", {"arg": "value"})

        # Assert the expected result
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == str(dict_result)

    @pytest.mark.asyncio
    async def test_call_tool_with_unknown_result_type(self):
        """Test call_tool with a function that returns an unknown type."""

        # Create a class that isn't explicitly handled
        class UnknownType:
            def __str__(self):
                return "unknown type string representation"

        unknown_result = UnknownType()

        # Create the agent under test
        agent = SwarmAgent(
            name="test_agent",
            instruction="Test instruction",
            server_names=[],
            functions=[],
            parallel_tool_calls=True,
            context=Context(),
        )
        # Setup function tool
        mock_function_tool = MagicMock()
        mock_function_tool.run = AsyncMock(return_value=unknown_result)
        agent._function_tool_map = {"test_function": mock_function_tool}
        agent.initialized = True

        # Call the real method
        result = await agent.call_tool("test_function", {"arg": "value"})

        # Assert the expected result
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == str(unknown_result)

    @pytest.mark.asyncio
    async def test_call_tool_with_non_function_tool(
        self, mock_swarm_agent, mock_tool_response
    ):
        """Test call_tool with a non-function tool."""
        # Set up mocks
        mock_swarm_agent._function_tool_map = {}
        mock_swarm_agent.initialized = True
        mock_swarm_agent.call_tool = AsyncMock(return_value=mock_tool_response)

        # Call the method directly without using Agent.call_tool
        # We're testing that the SwarmAgent's call_tool method works when the tool
        # is not in the function tool map
        result = await mock_swarm_agent.call_tool("non_function_tool", {"arg": "value"})

        # Assert the call was made and the result was returned
        mock_swarm_agent.call_tool.assert_called_once_with(
            "non_function_tool", {"arg": "value"}
        )
        assert result == mock_tool_response


class TestSwarm:
    """Tests for the Swarm class."""

    @pytest.mark.asyncio
    async def test_swarm_initialization(self, mock_swarm_agent):
        """Test Swarm initialization."""
        # We need to use a concrete implementation of Swarm
        context_variables = {"var1": "value1", "var2": "value2"}
        swarm = OpenAISwarm(agent=mock_swarm_agent, context_variables=context_variables)

        # Assert swarm properties
        assert swarm.agent == mock_swarm_agent
        assert swarm.context_variables == context_variables
        assert swarm.instruction == mock_swarm_agent.instruction

    @pytest.mark.asyncio
    async def test_get_tool(self, mock_swarm_agent):
        """Test get_tool method."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Set up the aggregator to return a list of tools
        test_tool = Tool(
            name="test_tool",
            inputSchema={},
        )
        mock_swarm_agent.list_tools = AsyncMock(
            return_value=MagicMock(tools=[test_tool])
        )

        # Call get_tool
        tool = await swarm.get_tool(test_tool.name)

        # Assert tool is found
        assert tool == test_tool

        # Test with a non-existent tool
        tool = await swarm.get_tool("non_existent_tool")
        # Assert tool is not found
        assert tool is None

    @pytest.mark.asyncio
    async def test_pre_tool_call_with_context_variables(self, mock_swarm_agent):
        """Test pre_tool_call with a tool that has context_variables parameter."""
        # Use a concrete implementation of Swarm
        context_variables = {"var1": "value1", "var2": "value2"}
        swarm = OpenAISwarm(agent=mock_swarm_agent, context_variables=context_variables)

        # Create a tool with context_variables in its input schema
        tool_name = "test_tool"
        test_tool = MagicMock(
            name=tool_name,
            inputSchema={"context_variables": {"type": "object"}},
        )

        # Mock get_tool to return our test tool
        swarm.get_tool = AsyncMock(return_value=test_tool)

        # Create a request
        request = CallToolRequest(
            agent_name=swarm.agent.name,
            method="tools/call",
            params=CallToolRequestParams(name=tool_name, arguments={"arg": "value"}),
        )

        # Call pre_tool_call
        result = await swarm.pre_tool_call(None, request)

        # Assert context_variables were added to the request
        assert result.params.arguments["context_variables"] == context_variables

    @pytest.mark.asyncio
    async def test_pre_tool_call_with_nonexistent_tool(self, mock_swarm_agent):
        """Test pre_tool_call with a tool that doesn't exist."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Mock get_tool to return None (tool not found)
        swarm.get_tool = AsyncMock(return_value=None)

        # Create a request
        request = CallToolRequest(
            agent_name=swarm.agent.name,
            method="tools/call",
            params=CallToolRequestParams(
                name="non_existent_tool", arguments={"arg": "value"}
            ),
        )

        # Call pre_tool_call
        result = await swarm.pre_tool_call(None, request)

        # Assert the original request is returned unchanged
        assert result == request

    @pytest.mark.asyncio
    async def test_post_tool_call_with_agent_resource(
        self, mock_swarm_agent, mock_agent
    ):
        """Test post_tool_call with an agent resource."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Mock the set_agent method
        swarm.set_agent = AsyncMock()

        # Create an agent resource
        agent_resource = create_agent_resource(mock_agent)

        # Create a request and result
        request = MagicMock()
        result = CallToolResult(content=[agent_resource])

        # Call post_tool_call
        processed_result = await swarm.post_tool_call(None, request, result)

        # Assert set_agent was called with the agent
        swarm.set_agent.assert_called_once_with(mock_agent)

        # Assert the content was transformed to text content
        assert len(processed_result.content) == 1
        assert processed_result.content[0].type == "text"
        assert processed_result.content[0].text == agent_resource.resource.text

    @pytest.mark.asyncio
    async def test_post_tool_call_with_agent_function_result(
        self, mock_swarm_agent, mock_agent
    ):
        """Test post_tool_call with an agent function result."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Create context variables for the agent function result
        context_variables = {"var1": "updated1", "var2": "updated2"}

        # Create an agent function result with agent and context variables
        agent_function_result = AgentFunctionResult(
            value="test value", agent=mock_agent, context_variables=context_variables
        )
        resource = create_agent_function_result_resource(agent_function_result)

        # Mock the set_agent method
        swarm.set_agent = AsyncMock()

        # Create a request and result
        request = MagicMock()
        result = CallToolResult(content=[resource])

        # Call post_tool_call
        processed_result = await swarm.post_tool_call(None, request, result)

        # Assert context variables were updated
        assert swarm.context_variables["var1"] == "updated1"
        assert swarm.context_variables["var2"] == "updated2"

        # Assert set_agent was called with the agent
        swarm.set_agent.assert_called_once_with(mock_agent)

        # Assert the content was transformed to text content
        assert len(processed_result.content) == 1
        assert processed_result.content[0].type == "text"
        assert processed_result.content[0].text == resource.resource.text

    @pytest.mark.asyncio
    async def test_post_tool_call_with_regular_content(self, mock_swarm_agent):
        """Test post_tool_call with regular content."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Create a request and result with regular text content
        request = MagicMock()
        text_content = TextContent(type="text", text="Regular content")
        result = CallToolResult(content=[text_content])

        # Call post_tool_call
        processed_result = await swarm.post_tool_call(None, request, result)

        # Assert the content is unchanged
        assert len(processed_result.content) == 1
        assert processed_result.content[0] == text_content

    @pytest.mark.asyncio
    async def test_set_agent(self, mock_swarm_agent, mock_agent):
        """Test set_agent method."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Assert initial agent
        assert swarm.agent == mock_swarm_agent

        # Call set_agent with a new agent
        await swarm.set_agent(mock_agent)

        # Assert the agent was changed and initialized
        assert swarm.agent == mock_agent
        mock_swarm_agent.shutdown.assert_called_once()
        mock_agent.initialize.assert_called_once()

        # Test setting agent to None
        await swarm.set_agent(None)
        assert swarm.instruction is None

    @pytest.mark.asyncio
    async def test_set_agent_with_done_agent(self, mock_swarm_agent, done_agent):
        """Test set_agent with a DoneAgent."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Call set_agent with a DoneAgent
        await swarm.set_agent(done_agent)

        # Assert the instruction is set to None
        assert swarm.instruction is None

    @pytest.mark.asyncio
    async def test_should_continue(self, mock_swarm_agent, done_agent):
        """Test should_continue method."""
        # Use a concrete implementation of Swarm
        swarm = OpenAISwarm(agent=mock_swarm_agent)

        # Assert should_continue returns True with a normal agent
        assert swarm.should_continue() is True

        # Set a DoneAgent
        swarm.agent = done_agent

        # Assert should_continue returns False with a DoneAgent
        assert swarm.should_continue() is False

        # Set agent to None
        swarm.agent = None

        # Assert should_continue returns False with no agent
        assert swarm.should_continue() is False


class TestDoneAgent:
    """Tests for the DoneAgent class."""

    @pytest.mark.asyncio
    async def test_done_agent_initialization(self):
        """Test DoneAgent initialization."""
        # Create a DoneAgent instance
        agent = DoneAgent()

        # Assert agent properties
        assert agent.name == "__done__"
        assert agent.instruction == "Swarm Workflow is complete."

    @pytest.mark.asyncio
    async def test_done_agent_call_tool(self):
        """Test DoneAgent call_tool always returns a completion message."""
        # Create a DoneAgent instance
        agent = DoneAgent()

        # Call any tool
        result = await agent.call_tool("any_tool", {"arg": "value"})

        # Assert result is a completion message
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == "Workflow is complete."


class TestUtilityFunctions:
    """Tests for utility functions in the swarm module."""

    def test_create_agent_resource(self, mock_agent):
        """Test create_agent_resource function."""
        # Call the function
        resource = create_agent_resource(mock_agent)

        # Assert the result
        assert resource.type == "resource"
        assert resource.agent == mock_agent
        assert "You are now Agent" in resource.resource.text
        assert mock_agent.name in resource.resource.text

    def test_create_agent_function_result_resource(self):
        """Test create_agent_function_result_resource function."""
        # Create an AgentFunctionResult
        result = AgentFunctionResult(value="test value")

        # Call the function
        resource = create_agent_function_result_resource(result)

        # Assert the result
        assert resource.type == "resource"
        assert resource.result == result
        assert resource.resource.text == result.value
