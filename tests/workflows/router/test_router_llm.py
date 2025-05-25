import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent.workflows.router.router_base import (
    AgentRouterCategory,
    RouterCategory,
    ServerRouterCategory,
)
from mcp_agent.workflows.router.router_llm import (
    LLMRouter,
    LLMRouterResult,
    StructuredResponse,
    StructuredResponseCategory,
    DEFAULT_ROUTING_INSTRUCTION,
)


class TestLLMRouter:
    """Tests for the LLMRouter class."""

    # Test 1: Basic initialization
    def test_initialization(self, mock_context, mock_llm, mock_agent, test_function):
        """Tests basic initialization of the LLM router."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Assertions
        assert router is not None
        assert router.llm == mock_llm
        assert router.server_names == ["test_server"]
        assert router.agents == [mock_agent]
        assert router.functions == [test_function]
        assert router.context == mock_context
        assert router.initialized is False

    # Test 2: Factory method (create)
    @pytest.mark.asyncio
    async def test_create_factory_method(self, mock_context, mock_llm, mock_agent):
        """Tests the factory method for creating and initializing a router."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Create router using factory method
        router = await LLMRouter.create(
            llm=mock_llm,
            server_names=["test_server"],
            agents=[mock_agent],
            context=mock_context,
        )

        # Assertions
        assert router is not None
        assert router.initialized is True
        assert router.llm == mock_llm
        assert router.server_names == ["test_server"]
        assert router.agents == [mock_agent]
        assert router.context == mock_context
        assert len(router.server_categories) == 1
        assert len(router.agent_categories) == 1

    # Test 3: Default routing instruction
    def test_default_routing_instruction(self, mock_context, mock_llm):
        """Tests that the default routing instruction is used when none is provided."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            context=mock_context,
        )

        assert router.routing_instruction is None

        # We need to initialize the router to populate server_categories
        router.server_categories = {
            "test_server": MagicMock(
                name="test_server",
                description="A test server for routing",
                category="test_server",
            )
        }
        router.categories = router.server_categories

        # When accessing _generate_context, it should return content with server info
        prompt = router._generate_context()
        assert prompt is not None

        # Manually format the instruction to see the result
        formatted_instruction = DEFAULT_ROUTING_INSTRUCTION.format(
            context=prompt, request="test request", top_k=1
        )
        assert "test request" in formatted_instruction

    # Test 4: Custom routing instruction
    def test_custom_routing_instruction(self, mock_context, mock_llm):
        """Tests that a custom routing instruction is used when provided."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        custom_instruction = "Custom routing instruction: {context}, {request}, {top_k}"

        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            routing_instruction=custom_instruction,
            context=mock_context,
        )

        assert router.routing_instruction == custom_instruction

        # We need to initialize the router to populate server_categories
        router.server_categories = {
            "test_server": MagicMock(
                name="test_server",
                description="A test server for routing",
                category="test_server",
            )
        }
        router.categories = router.server_categories

        # Manually prepare what _route_with_llm would do
        context = router._generate_context()
        formatted_instruction = custom_instruction.format(
            context=context, request="test request", top_k=1
        )

        assert "Custom routing instruction" in formatted_instruction
        assert "test request" in formatted_instruction

    # Test 5: Route with LLM
    @pytest.mark.asyncio
    async def test_route_with_llm(
        self, mock_context, mock_llm, mock_agent, test_function
    ):
        """Tests the _route_with_llm method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )
        await router.initialize()

        # Mock response from LLM
        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="test_server",
                    confidence="high",
                    reasoning="Matches server capabilities",
                ),
                StructuredResponseCategory(
                    category="test_agent",
                    confidence="medium",
                    reasoning="Potential agent match",
                ),
            ]
        )

        # Mock the generate_structured method
        mock_llm.generate_structured.reset_mock()
        mock_llm.generate_structured.return_value = mock_response

        # Test routing
        results = await router._route_with_llm("How can I get help?", top_k=2)

        # Assertions
        assert mock_llm.generate_structured.call_count == 1
        assert len(results) == 2
        assert results[0].result == "test_server"
        assert results[0].confidence == "high"
        assert results[0].reasoning == "Matches server capabilities"
        assert results[1].result == mock_agent
        assert results[1].confidence == "medium"
        assert results[1].reasoning == "Potential agent match"

    # Test 6: Route method
    @pytest.mark.asyncio
    async def test_route_method(self, mock_context, mock_llm, mock_agent):
        """Tests the route method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            agents=[mock_agent],
            context=mock_context,
        )

        # Create a spy on _route_with_llm
        router._route_with_llm = AsyncMock(
            return_value=[
                LLMRouterResult(
                    result="test_server",
                    confidence="high",
                    reasoning="Good server match",
                )
            ]
        )

        # Test route method
        results = await router.route("How can I get help?")

        # Assertions
        assert router._route_with_llm.call_count == 1
        assert len(results) == 1
        assert results[0].result == "test_server"
        assert results[0].confidence == "high"

        # Check only basic parameters in _route_with_llm call
        assert (
            router._route_with_llm.call_args[0][0] == "How can I get help?"
        )  # request
        assert router._route_with_llm.call_args[0][1] == 1  # top_k

    # Test 7: Route to server method
    @pytest.mark.asyncio
    async def test_route_to_server_method(self, mock_context, mock_llm):
        """Tests the route_to_server method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server1", "test_server2"],
            context=mock_context,
        )

        # Create a spy on _route_with_llm
        router._route_with_llm = AsyncMock(
            return_value=[
                LLMRouterResult(
                    result="test_server1",
                    confidence="high",
                    reasoning="Best server match",
                )
            ]
        )

        # Test route_to_server method
        results = await router.route_to_server("Show me server info", top_k=1)

        # Assertions
        assert router._route_with_llm.call_count == 1
        assert len(results) == 1
        assert results[0].result == "test_server1"

        # Check _route_with_llm parameters
        call_args = router._route_with_llm.call_args
        assert call_args[0][0] == "Show me server info"  # request
        assert call_args[0][1] == 1  # top_k
        assert call_args[1]["include_servers"] is True
        assert call_args[1]["include_agents"] is False
        assert call_args[1]["include_functions"] is False

    # Test 8: Route to agent method
    @pytest.mark.asyncio
    async def test_route_to_agent_method(self, mock_context, mock_llm, mock_agent):
        """Tests the route_to_agent method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            agents=[mock_agent],
            context=mock_context,
        )

        # Create a spy on _route_with_llm
        router._route_with_llm = AsyncMock(
            return_value=[
                LLMRouterResult(
                    result=mock_agent,
                    confidence="high",
                    reasoning="Perfect agent match",
                )
            ]
        )

        # Test route_to_agent method
        results = await router.route_to_agent("I need agent help", top_k=1)

        # Assertions
        assert router._route_with_llm.call_count == 1
        assert len(results) == 1
        assert results[0].result == mock_agent

        # Check _route_with_llm parameters
        call_args = router._route_with_llm.call_args
        assert call_args[0][0] == "I need agent help"  # request
        assert call_args[0][1] == 1  # top_k
        assert call_args[1]["include_servers"] is False
        assert call_args[1]["include_agents"] is True
        assert call_args[1]["include_functions"] is False

    # Test 9: Route to function method
    @pytest.mark.asyncio
    async def test_route_to_function_method(
        self, mock_context, mock_llm, test_function
    ):
        """Tests the route_to_function method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            functions=[test_function],
            context=mock_context,
        )

        # Create a spy on _route_with_llm
        router._route_with_llm = AsyncMock(
            return_value=[
                LLMRouterResult(
                    result=test_function,
                    confidence="high",
                    reasoning="Exact function match",
                )
            ]
        )

        # Test route_to_function method
        results = await router.route_to_function("Run the test function", top_k=1)

        # Assertions
        assert router._route_with_llm.call_count == 1
        assert len(results) == 1
        assert results[0].result == test_function

        # Check _route_with_llm parameters
        call_args = router._route_with_llm.call_args
        assert call_args[0][0] == "Run the test function"  # request
        assert call_args[0][1] == 1  # top_k
        assert call_args[1]["include_servers"] is False
        assert call_args[1]["include_agents"] is False
        assert call_args[1]["include_functions"] is True

    # Test 10: Empty LLM response
    @pytest.mark.asyncio
    async def test_empty_llm_response(self, mock_context, mock_llm):
        """Tests handling of empty response from the LLM."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            context=mock_context,
        )
        await router.initialize()

        # Mock empty response from LLM
        mock_llm.generate_structured.reset_mock()
        mock_llm.generate_structured.return_value = StructuredResponse(categories=[])

        # Test routing
        results = await router._route_with_llm("Unknown request")

        # Assertions
        assert mock_llm.generate_structured.call_count == 1
        assert len(results) == 0

    # Test 11: Invalid category in LLM response
    @pytest.mark.asyncio
    async def test_invalid_category_in_llm_response(self, mock_context, mock_llm):
        """Tests handling of invalid category in LLM response."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            context=mock_context,
        )
        await router.initialize()

        # Mock response with invalid category
        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="invalid_server",  # This doesn't exist
                    confidence="high",
                    reasoning="Invalid match",
                ),
                StructuredResponseCategory(
                    category="test_server",  # This one exists
                    confidence="medium",
                    reasoning="Valid match",
                ),
            ]
        )

        # Mock the generate_structured method
        mock_llm.generate_structured.reset_mock()
        mock_llm.generate_structured.return_value = mock_response

        # Test routing
        results = await router._route_with_llm("Test request")

        # Assertions
        assert mock_llm.generate_structured.call_count == 1
        assert len(results) == 1  # Only the valid category should be returned
        assert results[0].result == "test_server"
        assert results[0].confidence == "medium"

    # Test 12: Generate context
    def test_generate_context(self, mock_context, mock_llm, mock_agent, test_function):
        """Tests the _generate_context method."""
        mock_context.tracer = None
        mock_context.tracing_enabled = False
        # Setup router
        router = LLMRouter(
            llm=mock_llm,
            server_names=["test_server"],
            agents=[mock_agent],
            functions=[test_function],
            context=mock_context,
        )

        # Initialize the router by setting up categories manually
        router.server_categories = {
            "test_server": ServerRouterCategory(
                name="test_server",
                description="A test server for routing",
                category="test_server",
                tools=[],
            )
        }

        router.agent_categories = {
            mock_agent.name: AgentRouterCategory(
                name=mock_agent.name,
                description="Test agent description",
                category=mock_agent,
                servers=[],
            )
        }

        function_name = "test_function"
        router.function_categories = {
            function_name: RouterCategory(
                name=function_name,
                description="Test function description",
                category=test_function,
            )
        }

        router.categories = {
            **router.server_categories,
            **router.agent_categories,
            **router.function_categories,
        }

        # Test with all categories
        full_context = router._generate_context(
            include_servers=True,
            include_agents=True,
            include_functions=True,
        )
        assert "Server Category: test_server" in full_context
        assert f"Agent Category: {mock_agent.name}" in full_context
        assert "Function Category:" in full_context

        # Test with only servers
        server_context = router._generate_context(
            include_servers=True,
            include_agents=False,
            include_functions=False,
        )
        assert "Server Category: test_server" in server_context
        assert "Agent Category:" not in server_context
        assert "Function Category:" not in server_context

        # Test with only agents
        agent_context = router._generate_context(
            include_servers=False,
            include_agents=True,
            include_functions=False,
        )
        assert "Server Category:" not in agent_context
        assert f"Agent Category: {mock_agent.name}" in agent_context
        assert "Function Category:" not in agent_context

        # Test with only functions
        function_context = router._generate_context(
            include_servers=False,
            include_agents=False,
            include_functions=True,
        )
        assert "Server Category:" not in function_context
        assert "Agent Category:" not in function_context
        assert "Function Category:" in function_context
