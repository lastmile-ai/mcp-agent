import pytest
from unittest.mock import MagicMock
from typing import List

from mcp_agent.workflows.router.router_base import (
    Router,
    RouterResult,
    RouterCategory,
    ServerRouterCategory,
    AgentRouterCategory,
)


# Create a minimal concrete implementation of the abstract Router class for testing
class TestRouter(Router):
    """A concrete implementation of the abstract Router class for testing."""

    async def route(self, request: str, top_k: int = 1) -> List[RouterResult]:
        """Implementation of abstract method for testing."""
        # Simply return the first category
        if not self.categories:
            return []
        if self.server_names:
            return [RouterResult(result="test_server")]
        elif self.agents:
            return [RouterResult(result=self.agents[0])]
        elif self.functions:
            return [RouterResult(result=self.functions[0])]
        return []

    async def route_to_server(self, request: str, top_k: int = 1) -> List[RouterResult]:
        """Implementation of abstract method for testing."""
        if not self.server_names:
            return []
        return [RouterResult(result="test_server")]

    async def route_to_agent(self, request: str, top_k: int = 1) -> List[RouterResult]:
        """Implementation of abstract method for testing."""
        if not self.agents:
            return []
        return [RouterResult(result=self.agents[0])]

    async def route_to_function(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult]:
        """Implementation of abstract method for testing."""
        if not self.functions:
            return []
        return [RouterResult(result=self.functions[0])]


class TestRouterBase:
    """Tests for the Router base class functionality."""

    # Test 1: Basic initialization
    def test_initialization(self, mock_context, mock_agent, test_function):
        """Tests basic initialization of the router."""
        router = TestRouter(
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Assertions
        assert router is not None
        assert router.server_names == ["test_server"]
        assert router.agents == [mock_agent]
        assert router.functions == [test_function]
        assert router.context == mock_context
        assert router.server_registry == mock_context.server_registry
        assert router.initialized is False

    # Test 2: Initialization with empty inputs
    def test_initialization_with_empty_inputs(self, mock_context):
        """Tests initialization fails when no routing targets are provided."""
        with pytest.raises(ValueError):
            # Initialize with empty inputs
            _ = TestRouter(
                server_names=[],
                agents=[],
                functions=[],
                context=mock_context,
            )

    # Test 3: Initialization without server registry but with server names
    def test_initialization_without_server_registry(self, mock_context):
        """Tests initialization fails when server_names are provided but server_registry is not."""
        mock_context.server_registry = None

        with pytest.raises(ValueError):
            # Initialize with server names but no server registry
            _ = TestRouter(
                server_names=["test_server"],
                context=mock_context,
            )

    # Test 4: Initialize method
    @pytest.mark.asyncio
    async def test_initialize_method(self, mock_context, mock_agent, test_function):
        """Tests the initialize method populates categories correctly."""
        router = TestRouter(
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Initialize router
        await router.initialize()

        # Assertions
        assert router.initialized is True
        assert len(router.server_categories) == 1
        assert len(router.agent_categories) == 1
        assert len(router.function_categories) == 1
        assert len(router.categories) == 3

        # Verify server category
        server_category = router.server_categories["test_server"]
        assert server_category.name == "test_server"
        assert server_category.category == "test_server"

        # Verify agent category
        agent_category = router.agent_categories[mock_agent.name]
        assert agent_category.name == mock_agent.name
        assert agent_category.category == mock_agent
        assert len(agent_category.servers) == 1

        # Verify function category
        function_name = list(router.function_categories.keys())[0]  # Get first key
        function_category = router.function_categories[function_name]
        assert function_category.category == test_function

    # Test 5: Multiple initialize calls
    @pytest.mark.asyncio
    async def test_multiple_initialize_calls(self, mock_context, mock_agent):
        """Tests that multiple initialize calls don't re-initialize if already initialized."""
        router = TestRouter(
            server_names=["test_server"],
            agents=[mock_agent],
            context=mock_context,
        )

        # Initialize router first
        await router.initialize()
        assert router.initialized is True

        # Now reset the mock and create a spy on the get_server_category method
        router.get_server_category = MagicMock()

        # Initialize again
        await router.initialize()
        # Should not call get_server_category again since router is already initialized
        assert router.get_server_category.call_count == 0

    # Test 6: Category getters
    def test_category_getters(self, mock_context, mock_agent, test_function):
        """Tests the category getter methods."""
        router = TestRouter(
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Test server category getter
        server_category = router.get_server_category("test_server")
        assert isinstance(server_category, ServerRouterCategory)
        assert server_category.name == "test_server"
        assert server_category.category == "test_server"

        # Test agent category getter
        agent_category = router.get_agent_category(mock_agent)
        assert isinstance(agent_category, AgentRouterCategory)
        assert agent_category.name == mock_agent.name
        assert agent_category.category == mock_agent
        assert len(agent_category.servers) == 1

        # Test function category getter
        function_category = router.get_function_category(test_function)
        assert isinstance(function_category, RouterCategory)
        assert function_category.category == test_function

    # Test 7: Category formatting
    def test_category_formatting(self, test_router_categories):
        """Tests the format_category method."""
        router = TestRouter(server_names=["test_server"])

        # Format a server category with index
        server_category = test_router_categories["server_category"]
        formatted_server = router.format_category(server_category, index=1)
        assert "1. Server Category: test_server" in formatted_server
        assert "Description: A test server for routing" in formatted_server
        assert "Tools in server:" in formatted_server

        # Format an agent category without index
        agent_category = test_router_categories["agent_category"]
        formatted_agent = router.format_category(agent_category)
        assert "Agent Category: test_agent" in formatted_agent
        assert "Description: A test agent for routing" in formatted_agent
        assert "Servers in agent:" in formatted_agent

        # Format a function category
        function_category = test_router_categories["function_category"]
        formatted_function = router.format_category(function_category, index=3)
        assert "3. Function Category: test_function" in formatted_function
        assert "Description: A test function for routing" in formatted_function

    # Test 8: Tools formatting
    def test_tools_formatting(self):
        """Tests the _format_tools method."""
        router = TestRouter(server_names=["test_server"])

        # Test with no tools
        formatted_empty = router._format_tools([])
        assert "No tool information provided" in formatted_empty

        # Test with tools
        tool1 = MagicMock()
        tool1.name = "tool1"  # Use string value, not a mock
        tool1.description = "A test tool"  # Use string value, not a mock

        tool2 = MagicMock()
        tool2.name = "tool2"  # Use string value, not a mock
        tool2.description = "Another test tool"  # Use string value, not a mock

        tools = [tool1, tool2]
        formatted_tools = router._format_tools(tools)
        assert "- tool1: A test tool" in formatted_tools
        assert "- tool2: Another test tool" in formatted_tools

    # Test 9: Router with only servers
    @pytest.mark.asyncio
    async def test_router_with_only_servers(self, mock_context):
        """Tests router with only server names."""
        router = TestRouter(
            server_names=["test_server"],
            context=mock_context,
        )
        await router.initialize()

        # Test route method
        results = await router.route("test request")
        assert len(results) == 1
        assert results[0].result == "test_server"

        # Test route_to_server method
        server_results = await router.route_to_server("test request")
        assert len(server_results) == 1
        assert server_results[0].result == "test_server"

        # Test other routing methods return empty lists
        agent_results = await router.route_to_agent("test request")
        assert len(agent_results) == 0

        function_results = await router.route_to_function("test request")
        assert len(function_results) == 0

    # Test 10: Router with only agents
    @pytest.mark.asyncio
    async def test_router_with_only_agents(self, mock_context, mock_agent):
        """Tests router with only agents."""
        router = TestRouter(
            agents=[mock_agent],
            context=mock_context,
        )
        await router.initialize()

        # Test route method
        results = await router.route("test request")
        assert len(results) == 1
        assert results[0].result == mock_agent

        # Test route_to_agent method
        agent_results = await router.route_to_agent("test request")
        assert len(agent_results) == 1
        assert agent_results[0].result == mock_agent

        # Test other routing methods return empty lists
        server_results = await router.route_to_server("test request")
        assert len(server_results) == 0

        function_results = await router.route_to_function("test request")
        assert len(function_results) == 0

    # Test 11: Router with only functions
    @pytest.mark.asyncio
    async def test_router_with_only_functions(self, mock_context, test_function):
        """Tests router with only functions."""
        router = TestRouter(
            functions=[test_function],
            context=mock_context,
        )
        await router.initialize()

        # Test route method
        results = await router.route("test request")
        assert len(results) == 1
        assert results[0].result == test_function

        # Test route_to_function method
        function_results = await router.route_to_function("test request")
        assert len(function_results) == 1
        assert function_results[0].result == test_function

        # Test other routing methods return empty lists
        server_results = await router.route_to_server("test request")
        assert len(server_results) == 0

        agent_results = await router.route_to_agent("test request")
        assert len(agent_results) == 0
