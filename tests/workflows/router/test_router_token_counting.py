import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_agent.workflows.router.router_llm import (
    LLMRouter,
    StructuredResponse,
    StructuredResponseCategory,
)
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.tracing.token_counter import TokenCounter


class TestRouterTokenCounting:
    """Tests for token counting in Router workflows"""

    # Mock logger to avoid async issues in tests
    @pytest.fixture(autouse=True)
    def mock_logger(self):
        with patch("mcp_agent.tracing.token_counter.logger") as mock:
            mock.debug = MagicMock()
            mock.info = MagicMock()
            mock.warning = MagicMock()
            mock.error = MagicMock()
            yield mock

    @pytest.fixture
    def mock_context_with_token_counter(self):
        """Create a mock context with token counter"""
        context = MagicMock()
        context.server_registry = MagicMock()

        # Create a proper server config class like in conftest.py
        class ServerConfig:
            def __init__(self, name):
                self.name = name
                self.description = f"{name} description"

        # Create a function to return different configs for different servers
        def mock_get_server_config(server_name):
            return ServerConfig(server_name)

        context.server_registry.get_server_config.side_effect = mock_get_server_config
        context.model_selector = MagicMock()
        context.model_selector.select_model = MagicMock(return_value="test-model")
        context.tracer = None
        context.tracing_enabled = False

        # Add token counter
        context.token_counter = TokenCounter()

        return context

    @pytest.fixture
    def mock_augmented_llm_with_token_tracking(self):
        """Create a mock AugmentedLLM that tracks tokens"""

        class MockAugmentedLLMWithTokens(AugmentedLLM):
            def __init__(self, agent=None, context=None, **kwargs):
                super().__init__(context=context, **kwargs)
                self.agent = agent or MagicMock(name="MockAgent")
                self.generate_mock = AsyncMock()
                self.generate_str_mock = AsyncMock()
                self.generate_structured_mock = AsyncMock()

            async def generate(self, message, request_params=None):
                # This shouldn't be called by router
                raise NotImplementedError("Router should use generate_structured")

            async def generate_str(self, message, request_params=None):
                # This shouldn't be called by router
                raise NotImplementedError("Router should use generate_structured")

            async def generate_structured(
                self, message, response_model, request_params=None
            ):
                # Simulate token recording
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"router_llm_{self.name}", node_type="llm_call"
                    )
                    await self.context.token_counter.record_usage(
                        input_tokens=200,
                        output_tokens=100,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                return await self.generate_structured_mock(
                    message, response_model, request_params
                )

        return MockAugmentedLLMWithTokens

    @pytest.fixture
    def mock_router_llm(
        self, mock_context_with_token_counter, mock_augmented_llm_with_token_tracking
    ):
        """Create a mock LLM for router"""
        llm = mock_augmented_llm_with_token_tracking(
            context=mock_context_with_token_counter, name="router_llm"
        )
        return llm

    @pytest.fixture
    def mock_agents(self):
        """Create mock agents for routing"""
        return [
            Agent(name="data_processor", instruction="Process data requests"),
            Agent(name="query_handler", instruction="Handle query requests"),
            Agent(name="report_generator", instruction="Generate reports"),
        ]

    @pytest.fixture
    def test_functions(self):
        """Create test functions for routing"""

        def calculate_sum(a: int, b: int) -> int:
            """Calculate sum of two numbers"""
            return a + b

        def format_text(text: str) -> str:
            """Format text in uppercase"""
            return text.upper()

        return [calculate_sum, format_text]

    @pytest.mark.asyncio
    async def test_router_basic_token_tracking(
        self, mock_context_with_token_counter, mock_router_llm, mock_agents
    ):
        """Test basic token tracking in router"""
        # Create router
        # Factory should return the mock LLM instance so token tracking works
        router = LLMRouter(
            name="test_router",
            llm_factory=lambda agent: mock_router_llm,
            server_names=["test_server"],
            agents=mock_agents,
            context=mock_context_with_token_counter,
        )

        # Mock LLM response
        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="data_processor",
                    confidence="high",
                    reasoning="Request is about data processing",
                )
            ]
        )
        # Configure mock LLM to return response and simulate token tracking
        mock_router_llm.generate_structured_mock.return_value = mock_response

        # Push app context
        await mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Execute routing
        results = await router.route("Process this data", top_k=1)

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify results
        assert len(results) == 1
        assert results[0].result.name == "data_processor"
        assert results[0].confidence == "high"

        # Check token usage - router makes one LLM call
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 300  # 200 input + 100 output
        assert app_usage.input_tokens == 200
        assert app_usage.output_tokens == 100

        # Check global summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 300
        assert "test-model (test_provider)" in summary.model_usage

    @pytest.mark.asyncio
    async def test_router_multiple_routes_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_router_llm,
        mock_agents,
        test_functions,
    ):
        """Test token tracking when router returns multiple routes"""
        # Create router with all types
        router = LLMRouter(
            name="test_router",
            llm_factory=lambda agent: mock_router_llm,
            server_names=["test_server_1", "test_server_2"],
            agents=mock_agents[:2],
            functions=test_functions,
            context=mock_context_with_token_counter,
        )

        # Mock LLM response with multiple categories (including a server that exists
        # in the router's server_categories)
        mock_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="test_server_1",
                    confidence="high",
                    reasoning="Server match",
                ),
                StructuredResponseCategory(
                    category="data_processor",
                    confidence="medium",
                    reasoning="Agent match",
                ),
                StructuredResponseCategory(
                    category="calculate_sum",
                    confidence="low",
                    reasoning="Function match",
                ),
            ]
        )
        mock_router_llm.generate_structured_mock.return_value = mock_response

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "routing_workflow", "workflow"
        )

        # Execute routing with top_k=3 (should include server, agent, function)
        results = await router.route("Complex request", top_k=3)

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify results
        assert len(results) == 3
        assert results[0].result == "test_server_1"
        assert results[1].result.name == "data_processor"
        assert callable(results[2].result)

        # Check token usage - still just one LLM call
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 300

    @pytest.mark.asyncio
    async def test_router_specific_route_methods_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_router_llm,
        mock_agents,
        test_functions,
    ):
        """Test token tracking for specific route methods (route_to_server, route_to_agent, route_to_function)"""
        # Create router
        router = LLMRouter(
            name="test_router",
            llm_factory=lambda agent: mock_router_llm,
            server_names=["test_server"],
            agents=mock_agents,
            functions=test_functions,
            context=mock_context_with_token_counter,
        )

        # Push app context
        await mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Test route_to_server
        mock_router_llm.generate_structured_mock.return_value = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="test_server",
                    confidence="high",
                    reasoning="Server routing",
                )
            ]
        )

        # Ensure router has initialized categories (server list populated)
        await router.initialize()
        results = await router.route_to_server("Server request")
        assert len(results) == 1
        assert results[0].result == "test_server"

        # Test route_to_agent
        mock_router_llm.generate_structured_mock.return_value = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="query_handler",
                    confidence="high",
                    reasoning="Agent routing",
                )
            ]
        )

        results = await router.route_to_agent("Agent request")
        assert len(results) == 1
        assert results[0].result.name == "query_handler"

        # Test route_to_function
        mock_router_llm.generate_structured_mock.return_value = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="format_text",
                    confidence="high",
                    reasoning="Function routing",
                )
            ]
        )

        results = await router.route_to_function("Function request")
        assert len(results) == 1
        assert callable(results[0].result)

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Check token usage - 3 LLM calls total
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 900  # 3 calls x 300 tokens each
        assert app_usage.input_tokens == 600  # 3 x 200
        assert app_usage.output_tokens == 300  # 3 x 100

    @pytest.mark.asyncio
    async def test_router_empty_response_token_tracking(
        self, mock_context_with_token_counter, mock_router_llm, mock_agents
    ):
        """Test token tracking when router returns empty results"""
        # Create router
        router = LLMRouter(
            name="test_router",
            llm_factory=lambda agent: mock_router_llm,
            agents=mock_agents,
            context=mock_context_with_token_counter,
        )

        # Mock empty LLM response
        mock_router_llm.generate_structured_mock.return_value = StructuredResponse(
            categories=[]
        )

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "empty_routing", "workflow"
        )

        # Execute routing
        results = await router.route("Unknown request")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify empty results
        assert len(results) == 0

        # But tokens were still used for the LLM call
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 300

    @pytest.mark.asyncio
    async def test_router_nested_workflow_token_tracking(
        self, mock_context_with_token_counter, mock_router_llm, mock_agents
    ):
        """Test token tracking when router is used within a larger workflow"""
        # Create multiple routers for different purposes using the same mock factory
        general_router = LLMRouter(
            llm_factory=lambda agent: mock_router_llm,
            agents=mock_agents,
            context=mock_context_with_token_counter,
            routing_instruction="Route general requests",
        )

        specific_router = LLMRouter(
            llm_factory=lambda agent: mock_router_llm,
            server_names=["specialized_server"],
            context=mock_context_with_token_counter,
            routing_instruction="Route specialized requests",
        )

        # Mock responses
        general_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="data_processor",
                    confidence="high",
                    reasoning="General routing",
                )
            ]
        )

        specific_response = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="specialized_server",
                    confidence="high",
                    reasoning="Specific routing",
                )
            ]
        )

        # Push app context
        await mock_context_with_token_counter.token_counter.push("main_app", "app")

        # First routing decision
        await mock_context_with_token_counter.token_counter.push(
            "general_routing", "workflow"
        )
        mock_router_llm.generate_structured_mock.return_value = general_response
        await general_router.route("General request")
        general_node = await mock_context_with_token_counter.token_counter.pop()

        # Second routing decision
        await mock_context_with_token_counter.token_counter.push(
            "specific_routing", "workflow"
        )
        mock_router_llm.generate_structured_mock.return_value = specific_response
        await specific_router.route("Specific request")
        specific_node = await mock_context_with_token_counter.token_counter.pop()

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify individual routing token usage
        general_usage = general_node.aggregate_usage()
        assert general_usage.total_tokens == 300

        specific_usage = specific_node.aggregate_usage()
        assert specific_usage.total_tokens == 300

        # Verify app-level aggregation
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 600  # Total from both routers

        # Check global summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 600

    @pytest.mark.asyncio
    async def test_router_error_handling_token_tracking(
        self, mock_context_with_token_counter, mock_router_llm, mock_agents
    ):
        """Test that tokens are tracked even when routing errors occur"""
        # Create router
        router = LLMRouter(
            llm_factory=lambda agent: mock_router_llm,
            agents=mock_agents,
            context=mock_context_with_token_counter,
        )

        # Override generate_structured to directly mock and raise error
        async def generate_structured_with_error(
            message, response_model, request_params=None
        ):
            # Record tokens manually
            if mock_context_with_token_counter.token_counter:
                await mock_context_with_token_counter.token_counter.push(
                    name="router_llm_router_llm", node_type="llm_call"
                )
                await mock_context_with_token_counter.token_counter.record_usage(
                    input_tokens=150,
                    output_tokens=0,  # No output due to error
                    model_name="test-model",
                    provider="test_provider",
                )
                await mock_context_with_token_counter.token_counter.pop()
            # Then raise error
            raise Exception("LLM routing error")

        # Replace the method
        # Override classifier on the same mock instance
        mock_router_llm.generate_structured = generate_structured_with_error

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "error_workflow", "workflow"
        )

        # Execute routing (should raise error)
        with pytest.raises(Exception, match="LLM routing error"):
            await router.route("This will fail")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify tokens were still tracked before error
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 150
        assert workflow_usage.input_tokens == 150
        assert workflow_usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_router_with_custom_routing_instruction_token_tracking(
        self, mock_context_with_token_counter, mock_router_llm, mock_agents
    ):
        """Test token tracking with custom routing instructions"""
        # Create router with custom instruction
        custom_instruction = """
        You are a specialized router for customer support.
        Categories: {context}
        Request: {request}
        Select top {top_k} categories.
        """

        router = LLMRouter(
            llm_factory=lambda agent: mock_router_llm,
            agents=mock_agents,
            routing_instruction=custom_instruction,
            context=mock_context_with_token_counter,
        )

        # Mock response
        mock_router_llm.generate_structured_mock.return_value = StructuredResponse(
            categories=[
                StructuredResponseCategory(
                    category="query_handler",
                    confidence="high",
                    reasoning="Support query",
                )
            ]
        )

        # Push context
        await mock_context_with_token_counter.token_counter.push(
            "custom_routing", "workflow"
        )

        # Execute routing
        results = await router.route("Help with my account", top_k=2)

        # Pop context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Verify results and token usage
        assert len(results) == 1
        assert results[0].result.name == "query_handler"

        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 300
