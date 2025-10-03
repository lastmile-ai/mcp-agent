import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.workflows.parallel.fan_in import FanInInput
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
from mcp_agent.agents.agent import Agent
from mcp_agent.tracing.token_counter import TokenCounter


class TestParallelLLMTokenCounting:
    """Tests for token counting in the ParallelLLM workflow"""

    # Mock logger to avoid async issues in tests
    @pytest.fixture(autouse=True)
    def mock_logger(self):
        from unittest.mock import patch

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
        context.executor = MagicMock()
        context.executor.execute = AsyncMock()
        context.executor.execute_many = AsyncMock()
        context.model_selector = MagicMock()
        context.model_selector.select_model = MagicMock(return_value="test-model")
        context.tracer = None
        context.tracing_enabled = False

        # Add token counter
        context.token_counter = TokenCounter()

        return context

    @pytest.fixture
    def mock_augmented_llm_with_tokens(self):
        """Create a mock AugmentedLLM that tracks tokens"""

        class MockAugmentedLLMWithTokens(AugmentedLLM):
            def __init__(self, agent=None, context=None, token_multiplier=1, **kwargs):
                super().__init__(context=context, **kwargs)
                self.agent = agent or MagicMock(name="MockAgent")
                self.token_multiplier = token_multiplier
                self.generate_mock = AsyncMock()
                self.generate_str_mock = AsyncMock()
                self.generate_structured_mock = AsyncMock()

            async def generate(self, message, request_params=None):
                # Record token usage based on agent
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"llm_{self.agent.name}", node_type="llm_call"
                    )
                    # Vary tokens based on agent
                    await self.context.token_counter.record_usage(
                        input_tokens=100 * self.token_multiplier,
                        output_tokens=50 * self.token_multiplier,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                return await self.generate_mock(message, request_params)

            async def generate_str(self, message, request_params=None):
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"llm_str_{self.agent.name}", node_type="llm_call"
                    )
                    await self.context.token_counter.record_usage(
                        input_tokens=80 * self.token_multiplier,
                        output_tokens=40 * self.token_multiplier,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                return await self.generate_str_mock(message, request_params)

            async def generate_structured(
                self, message, response_model, request_params=None
            ):
                if self.context and self.context.token_counter:
                    await self.context.token_counter.push(
                        name=f"llm_structured_{self.agent.name}", node_type="llm_call"
                    )
                    await self.context.token_counter.record_usage(
                        input_tokens=120 * self.token_multiplier,
                        output_tokens=60 * self.token_multiplier,
                        model_name="test-model",
                        provider="test_provider",
                    )
                    await self.context.token_counter.pop()

                return await self.generate_structured_mock(
                    message, response_model, request_params
                )

        return MockAugmentedLLMWithTokens

    @pytest.fixture
    def mock_fan_out_agents(self):
        """Create mock agents for fan-out"""
        return [
            Agent(name="analyzer", instruction="Analyze the data"),
            Agent(name="summarizer", instruction="Summarize the findings"),
            Agent(name="validator", instruction="Validate the results"),
        ]

    @pytest.fixture
    def mock_fan_in_agent(self):
        """Create a mock agent for fan-in"""
        return Agent(name="aggregator", instruction="Aggregate all results")

    @pytest.fixture
    def mock_llm_factory_with_tokens(
        self, mock_context_with_token_counter, mock_augmented_llm_with_tokens
    ):
        """Create a mock LLM factory that creates token-tracking LLMs"""

        def factory(agent):
            # Use different token multipliers for different agents
            multiplier = {
                "analyzer": 1,
                "summarizer": 2,
                "validator": 3,
                "aggregator": 1,
            }.get(agent.name, 1)

            llm = mock_augmented_llm_with_tokens(
                agent=agent,
                context=mock_context_with_token_counter,
                token_multiplier=multiplier,
            )
            # Set up default mocks
            llm.generate_mock.return_value = [f"Response from {agent.name}"]
            llm.generate_str_mock.return_value = f"String response from {agent.name}"
            llm.generate_structured_mock.return_value = MagicMock(
                result=f"Structured response from {agent.name}"
            )
            return llm

        return factory

    @pytest.mark.asyncio
    async def test_parallel_llm_token_tracking_basic(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_out_agents,
        mock_fan_in_agent,
    ):
        """Test basic token tracking in ParallelLLM workflow"""
        # Create ParallelLLM
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_fan_in_agent,
            fan_out_agents=mock_fan_out_agents,
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
            name="parallel_workflow",
        )

        # Mock executor.execute_many to simulate parallel execution
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                result = await task
                results.append(result)
            return results

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many
        )

        # Push app context
        await mock_context_with_token_counter.token_counter.push("test_app", "app")

        # Execute parallel workflow
        result = await parallel_llm.generate("Analyze this data")

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Check results
        assert len(result) == 1
        assert result[0] == "Response from aggregator"

        # Check token usage
        # Fan-out agents:
        # - analyzer: 100 + 50 = 150 tokens
        # - summarizer: 200 + 100 = 300 tokens (2x multiplier)
        # - validator: 300 + 150 = 450 tokens (3x multiplier)
        # Fan-in aggregator: 100 + 50 = 150 tokens
        # Total: 1050 tokens
        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 1050
        assert app_usage.input_tokens == 700  # 100 + 200 + 300 + 100
        assert app_usage.output_tokens == 350  # 50 + 100 + 150 + 50

        # Check global summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 1050

    @pytest.mark.asyncio
    async def test_parallel_llm_token_tracking_with_functions(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_in_agent,
    ):
        """Test token tracking when using functions in fan-out"""

        # Create mock functions
        def function1(message):
            return "Function 1 result"

        def function2(message):
            return "Function 2 result"

        # Create ParallelLLM with functions
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_fan_in_agent,
            fan_out_functions=[function1, function2],
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Mock executor
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                if asyncio.iscoroutine(task):
                    result = await task
                else:
                    # It's a partial function
                    result = task()
                results.append(result)
            return results

        import asyncio

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many
        )

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "parallel_workflow", "workflow"
        )

        # Execute
        result = await parallel_llm.generate("Process this")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Check results
        assert result == ["Response from aggregator"]

        # Only the aggregator should have recorded tokens
        # Functions don't use tokens
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 150  # Only aggregator tokens
        assert workflow_usage.input_tokens == 100
        assert workflow_usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_parallel_llm_generate_str_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_out_agents,
        mock_fan_in_agent,
    ):
        """Test token tracking for generate_str method"""
        # Create ParallelLLM
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_fan_in_agent,
            fan_out_agents=mock_fan_out_agents[:2],  # Use only 2 agents
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Mock executor
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                result = await task
                results.append(result)
            return results

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many
        )

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "str_workflow", "workflow"
        )

        # Execute generate_str
        result_str = await parallel_llm.generate_str("Generate string output")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Check result
        assert result_str == "String response from aggregator"

        # Check token usage for generate_str
        # ParallelLLM.generate_str calls fan_out.generate() (not generate_str())
        # So fan-out agents use generate() tokens (100/50):
        # - analyzer: 100 + 50 = 150 tokens
        # - summarizer: 200 + 100 = 300 tokens (2x multiplier)
        # Fan-in aggregator uses generate_str: 80 + 40 = 120 tokens
        # Total: 570 tokens
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 570
        assert workflow_usage.input_tokens == 380  # 100 + 200 + 80
        assert workflow_usage.output_tokens == 190  # 50 + 100 + 40

    @pytest.mark.asyncio
    async def test_parallel_llm_custom_fan_in_function_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_out_agents,
    ):
        """Test token tracking when using a custom fan-in function"""

        # Create custom fan-in function
        async def custom_fan_in(responses: FanInInput) -> str:
            # Custom logic that doesn't use LLM (no tokens)
            all_responses = []
            for agent_name, agent_responses in responses.items():
                all_responses.extend(agent_responses)
            return f"Aggregated {len(all_responses)} responses"

        # Create ParallelLLM with custom fan-in
        parallel_llm = ParallelLLM(
            fan_in_agent=custom_fan_in,
            fan_out_agents=mock_fan_out_agents,
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Mock executor
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                result = await task
                results.append(result)
            return results

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many
        )

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "custom_fan_in_workflow", "workflow"
        )

        # Execute
        result = await parallel_llm.generate("Process with custom aggregation")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Check result
        assert result == "Aggregated 3 responses"

        # Only fan-out agents should have recorded tokens
        # Custom fan-in doesn't use tokens
        # - analyzer: 150 tokens
        # - summarizer: 300 tokens
        # - validator: 450 tokens
        # Total: 900 tokens (no fan-in tokens)
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 900
        assert workflow_usage.input_tokens == 600  # 100 + 200 + 300
        assert workflow_usage.output_tokens == 300  # 50 + 100 + 150

    @pytest.mark.asyncio
    async def test_parallel_llm_nested_workflows_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_out_agents,
        mock_fan_in_agent,
    ):
        """Test token tracking with nested ParallelLLM workflows"""
        # Create inner parallel workflow
        inner_parallel = ParallelLLM(
            fan_in_agent=Agent(
                name="inner_aggregator", instruction="Inner aggregation"
            ),
            fan_out_agents=[
                Agent(name="inner_agent_1", instruction="Inner processing 1"),
                Agent(name="inner_agent_2", instruction="Inner processing 2"),
            ],
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
            name="inner_parallel",
        )

        # Create outer parallel workflow that includes inner as one of the fan-out
        outer_parallel = ParallelLLM(
            fan_in_agent=mock_fan_in_agent,
            fan_out_agents=[mock_fan_out_agents[0], inner_parallel],
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
            name="outer_parallel",
        )

        # Mock executor
        async def mock_execute_many(tasks):
            results = []
            for task in tasks:
                result = await task
                results.append(result)
            return results

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many
        )

        # Push app context
        await mock_context_with_token_counter.token_counter.push("nested_app", "app")

        # Execute outer workflow
        await outer_parallel.generate("Nested parallel processing")

        # Pop app context
        app_node = await mock_context_with_token_counter.token_counter.pop()

        # Calculate expected tokens:
        # Outer fan-out:
        #   - analyzer: 150 tokens
        #   - inner_parallel:
        #     - inner_agent_1: 150 tokens
        #     - inner_agent_2: 150 tokens
        #     - inner_aggregator: 150 tokens
        #     Total inner: 450 tokens
        # Outer fan-in (aggregator): 150 tokens
        # Total: 150 + 450 + 150 = 750 tokens

        app_usage = app_node.aggregate_usage()
        assert app_usage.total_tokens == 750

        # Check by model in summary
        summary = await mock_context_with_token_counter.token_counter.get_summary()
        assert summary.usage.total_tokens == 750
        assert "test-model (test_provider)" in summary.model_usage

    @pytest.mark.asyncio
    async def test_parallel_llm_error_handling_token_tracking(
        self,
        mock_context_with_token_counter,
        mock_llm_factory_with_tokens,
        mock_fan_out_agents,
        mock_fan_in_agent,
    ):
        """Test that tokens are tracked even when errors occur"""
        # Create ParallelLLM
        parallel_llm = ParallelLLM(
            fan_in_agent=mock_fan_in_agent,
            fan_out_agents=mock_fan_out_agents[:2],
            llm_factory=mock_llm_factory_with_tokens,
            context=mock_context_with_token_counter,
        )

        # Mock executor to track first agent then fail
        async def mock_execute_many_with_error(tasks):
            results = []
            for i, task in enumerate(tasks):
                if i == 0:
                    # First task succeeds
                    result = await task
                    results.append(result)
                else:
                    # Second task fails
                    raise Exception("Fan-out execution error")
            return results

        mock_context_with_token_counter.executor.execute_many = AsyncMock(
            side_effect=mock_execute_many_with_error
        )

        # Push workflow context
        await mock_context_with_token_counter.token_counter.push(
            "error_workflow", "workflow"
        )

        # Execute (should raise error)
        with pytest.raises(Exception, match="Fan-out execution error"):
            await parallel_llm.generate("This will fail")

        # Pop workflow context
        workflow_node = await mock_context_with_token_counter.token_counter.pop()

        # Only the first agent should have recorded tokens before error
        workflow_usage = workflow_node.aggregate_usage()
        assert workflow_usage.total_tokens == 150  # Only analyzer tokens
        assert workflow_usage.input_tokens == 100
        assert workflow_usage.output_tokens == 50
