"""Tests for TokenCounter implementation"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

from mcp_agent.tracing.token_counter import (
    TokenCounter,
    TokenUsage,
    TokenNode,
)
from mcp_agent.workflows.llm.llm_selector import (
    ModelInfo,
    ModelCost,
    ModelMetrics,
    ModelLatency,
    ModelBenchmarks,
)


class TestTokenUsage:
    """Test TokenUsage dataclass"""

    def test_token_usage_initialization(self):
        """Test TokenUsage initialization and auto-calculation of total"""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150
        assert usage.model_name is None
        assert usage.model_info is None
        assert isinstance(usage.timestamp, datetime)

    def test_token_usage_explicit_total(self):
        """Test that explicit total_tokens is preserved"""
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=200)
        assert usage.total_tokens == 200  # Should not be overwritten


class TestTokenNode:
    """Test TokenNode dataclass"""

    def test_token_node_initialization(self):
        """Test TokenNode initialization"""
        node = TokenNode(name="test_node", node_type="agent")
        assert node.name == "test_node"
        assert node.node_type == "agent"
        assert node.parent is None
        assert node.children == []
        assert isinstance(node.usage, TokenUsage)
        assert node.metadata == {}

    def test_add_child(self):
        """Test adding child nodes"""
        parent = TokenNode(name="parent", node_type="app")
        child = TokenNode(name="child", node_type="agent")

        parent.add_child(child)

        assert len(parent.children) == 1
        assert parent.children[0] == child
        assert child.parent == parent

    def test_aggregate_usage_single_node(self):
        """Test aggregate usage for single node"""
        node = TokenNode(name="test", node_type="agent")
        node.usage = TokenUsage(input_tokens=100, output_tokens=50)

        aggregated = node.aggregate_usage()
        assert aggregated.input_tokens == 100
        assert aggregated.output_tokens == 50
        assert aggregated.total_tokens == 150

    def test_aggregate_usage_with_children(self):
        """Test aggregate usage with child nodes"""
        root = TokenNode(name="root", node_type="app")
        root.usage = TokenUsage(input_tokens=100, output_tokens=50)

        child1 = TokenNode(name="child1", node_type="agent")
        child1.usage = TokenUsage(input_tokens=200, output_tokens=100)

        child2 = TokenNode(name="child2", node_type="agent")
        child2.usage = TokenUsage(input_tokens=150, output_tokens=75)

        root.add_child(child1)
        root.add_child(child2)

        aggregated = root.aggregate_usage()
        assert aggregated.input_tokens == 450  # 100 + 200 + 150
        assert aggregated.output_tokens == 225  # 50 + 100 + 75
        assert aggregated.total_tokens == 675

    def test_to_dict(self):
        """Test converting node to dictionary"""
        node = TokenNode(name="test", node_type="agent", metadata={"key": "value"})
        node.usage = TokenUsage(input_tokens=100, output_tokens=50, model_name="gpt-4")

        result = node.to_dict()

        assert result["name"] == "test"
        assert result["type"] == "agent"
        assert result["metadata"] == {"key": "value"}
        assert result["usage"]["input_tokens"] == 100
        assert result["usage"]["output_tokens"] == 50
        assert result["usage"]["total_tokens"] == 150
        assert result["usage"]["model_name"] == "gpt-4"
        assert "timestamp" in result["usage"]
        assert result["children"] == []


class TestTokenCounter:
    """Test TokenCounter class"""

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
    def mock_models(self):
        """Create mock models for testing"""
        models = [
            ModelInfo(
                name="gpt-4",
                provider="OpenAI",
                description="GPT-4",
                context_window=8192,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        input_cost_per_1m=10.0,
                        output_cost_per_1m=30.0,
                        blended_cost_per_1m=15.0,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=50.0, tokens_per_second=100.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.8),
                ),
            ),
            ModelInfo(
                name="claude-3-opus",
                provider="Anthropic",
                description="Claude 3 Opus",
                context_window=200000,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        input_cost_per_1m=15.0,
                        output_cost_per_1m=75.0,
                        blended_cost_per_1m=30.0,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=40.0, tokens_per_second=120.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.9),
                ),
            ),
            ModelInfo(
                name="claude-3-opus",
                provider="AWS Bedrock",
                description="Claude 3 Opus on Bedrock",
                context_window=200000,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        input_cost_per_1m=20.0,
                        output_cost_per_1m=80.0,
                        blended_cost_per_1m=35.0,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=60.0, tokens_per_second=80.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.9),
                ),
            ),
        ]
        return models

    @pytest.fixture
    def token_counter(self, mock_models):
        """Create a TokenCounter with mocked model loading"""
        with patch(
            "mcp_agent.tracing.token_counter.load_default_models",
            return_value=mock_models,
        ):
            return TokenCounter()

    def test_initialization(self, token_counter, mock_models):
        """Test TokenCounter initialization"""
        assert token_counter._stack == []
        assert token_counter._root is None
        assert token_counter._current is None
        assert len(token_counter._models) == 3
        assert ("openai", "gpt-4") in token_counter._model_costs
        assert ("anthropic", "claude-3-opus") in token_counter._model_costs

    @pytest.mark.asyncio
    async def test_push_pop_single(self, token_counter):
        """Test push and pop operations"""
        await token_counter.push("app", "app")

        assert len(token_counter._stack) == 1
        assert token_counter._current.name == "app"
        assert token_counter._root == token_counter._current

        popped = await token_counter.pop()
        assert popped.name == "app"
        assert len(token_counter._stack) == 0
        assert token_counter._current is None

    @pytest.mark.asyncio
    async def test_push_pop_nested(self, token_counter):
        """Test nested push and pop operations"""
        await token_counter.push("app", "app")
        await token_counter.push("workflow", "workflow")
        await token_counter.push("agent", "agent")

        assert len(token_counter._stack) == 3
        assert await token_counter.get_current_path() == ["app", "workflow", "agent"]

        # Pop agent
        agent_node = await token_counter.pop()
        assert agent_node.name == "agent"
        assert token_counter._current.name == "workflow"

        # Pop workflow
        workflow_node = await token_counter.pop()
        assert workflow_node.name == "workflow"
        assert token_counter._current.name == "app"

        # Pop app
        app_node = await token_counter.pop()
        assert app_node.name == "app"
        assert token_counter._current is None

    @pytest.mark.asyncio
    async def test_pop_empty_stack(self, token_counter):
        """Test popping from empty stack"""
        result = await token_counter.pop()
        assert result is None

    @pytest.mark.asyncio
    async def test_record_usage_no_context(self, token_counter):
        """Test recording usage without context creates root"""
        await token_counter.record_usage(
            input_tokens=100, output_tokens=50, model_name="gpt-4", provider="OpenAI"
        )

        assert token_counter._root is not None
        assert token_counter._root.name == "root"
        assert token_counter._root.usage.input_tokens == 100
        assert token_counter._root.usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_record_usage_with_context(self, token_counter):
        """Test recording usage with context"""
        await token_counter.push("test", "agent")

        await token_counter.record_usage(
            input_tokens=100, output_tokens=50, model_name="gpt-4", provider="OpenAI"
        )

        assert token_counter._current.usage.input_tokens == 100
        assert token_counter._current.usage.output_tokens == 50
        assert token_counter._current.usage.model_name == "gpt-4"

        # Check global tracking
        assert ("gpt-4", "OpenAI") in token_counter._usage_by_model
        usage = token_counter._usage_by_model[("gpt-4", "OpenAI")]
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_record_usage_multiple_providers(self, token_counter):
        """Test recording usage for same model from different providers"""
        await token_counter.push("test", "app")

        # Record usage for Anthropic's Claude
        await token_counter.record_usage(
            input_tokens=100,
            output_tokens=50,
            model_name="claude-3-opus",
            provider="Anthropic",
        )

        # Record usage for Bedrock's Claude
        await token_counter.record_usage(
            input_tokens=200,
            output_tokens=100,
            model_name="claude-3-opus",
            provider="AWS Bedrock",
        )

        # Check they're tracked separately
        anthropic_usage = token_counter._usage_by_model[("claude-3-opus", "Anthropic")]
        assert anthropic_usage.input_tokens == 100
        assert anthropic_usage.output_tokens == 50

        bedrock_usage = token_counter._usage_by_model[("claude-3-opus", "AWS Bedrock")]
        assert bedrock_usage.input_tokens == 200
        assert bedrock_usage.output_tokens == 100

    def test_find_model_info_exact_match(self, token_counter):
        """Test finding model info by exact match"""
        # Without provider - should return first match
        model = token_counter.find_model_info("gpt-4")
        assert model is not None
        assert model.name == "gpt-4"
        assert model.provider == "OpenAI"

        # With provider - should return exact match
        model = token_counter.find_model_info("claude-3-opus", "AWS Bedrock")
        assert model is not None
        assert model.provider == "AWS Bedrock"

    def test_find_model_info_fuzzy_match(self, token_counter):
        """Test fuzzy matching for model info"""
        # Partial match
        model = token_counter.find_model_info("gpt-4-turbo")  # Not exact
        assert model is not None
        assert model.name == "gpt-4"

        # With provider hint
        model = token_counter.find_model_info("claude-3", "Anthropic")
        assert model is not None
        assert model.name == "claude-3-opus"
        assert model.provider == "Anthropic"

    def test_calculate_cost(self, token_counter):
        """Test cost calculation"""
        # GPT-4 cost calculation
        cost = token_counter.calculate_cost("gpt-4", 1000, 500, "OpenAI")
        expected = (1000 / 1_000_000) * 10.0 + (500 / 1_000_000) * 30.0
        assert cost == pytest.approx(expected)

        # Unknown model - should use default
        cost = token_counter.calculate_cost("unknown-model", 1000, 500)
        expected = (1500 * 0.5) / 1_000_000
        assert cost == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_get_summary(self, token_counter):
        """Test getting summary of token usage"""
        await token_counter.push("app", "app")

        # Record some usage
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await token_counter.record_usage(200, 100, "claude-3-opus", "Anthropic")
        await token_counter.record_usage(150, 75, "claude-3-opus", "AWS Bedrock")

        summary = await token_counter.get_summary()

        # Check total usage
        assert summary.usage.input_tokens == 450
        assert summary.usage.output_tokens == 225
        assert summary.usage.total_tokens == 675

        # Check by model
        assert "gpt-4 (OpenAI)" in summary.model_usage
        assert "claude-3-opus (Anthropic)" in summary.model_usage
        assert "claude-3-opus (AWS Bedrock)" in summary.model_usage

        # Check costs are calculated
        assert summary.cost > 0
        assert summary.model_usage["gpt-4 (OpenAI)"].cost > 0

    @pytest.mark.asyncio
    async def test_get_tree(self, token_counter):
        """Test getting token usage tree"""
        await token_counter.push("app", "app", {"version": "1.0"})
        await token_counter.push("agent", "agent")
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")

        tree = await token_counter.get_tree()

        assert tree is not None
        assert tree["name"] == "app"
        assert tree["type"] == "app"
        assert tree["metadata"] == {"version": "1.0"}
        assert len(tree["children"]) == 1
        assert tree["children"][0]["name"] == "agent"

    @pytest.mark.asyncio
    async def test_reset(self, token_counter):
        """Test resetting token counter"""
        await token_counter.push("app", "app")
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")

        await token_counter.reset()

        assert len(token_counter._stack) == 0
        assert token_counter._root is None
        assert token_counter._current is None
        assert len(token_counter._usage_by_model) == 0

    @pytest.mark.asyncio
    async def test_thread_safety(self, token_counter):
        """Test basic thread safety with concurrent operations"""
        import asyncio

        results = []

        async def worker(worker_id):
            for i in range(5):
                await token_counter.push(f"worker_{worker_id}_{i}", "agent")
                await token_counter.record_usage(10, 5, "gpt-4", "OpenAI")
                await asyncio.sleep(0.001)  # Small delay to encourage interleaving
                node = await token_counter.pop()
                if node:
                    results.append((worker_id, node.usage.total_tokens))

        # Run workers concurrently
        await asyncio.gather(*[worker(i) for i in range(3)])

        # All operations should complete without error
        assert len(results) == 15  # 3 workers * 5 iterations

        # Each result should have correct token count
        for _, tokens in results:
            assert tokens == 15  # 10 + 5

    def test_fuzzy_match_prefers_prefix(self, token_counter):
        """Test fuzzy matching prefers models where search term is a prefix"""
        # Add models that could cause fuzzy match confusion
        models = [
            ModelInfo(
                name="gpt-4o",
                provider="OpenAI",
                description="GPT-4o",
                context_window=128000,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(blended_cost_per_1m=7.5),
                    speed=ModelLatency(
                        time_to_first_token_ms=50.0, tokens_per_second=100.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.8),
                ),
            ),
            ModelInfo(
                name="gpt-4o-mini-2024-07-18",
                provider="OpenAI",
                description="GPT-4o mini",
                context_window=128000,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(blended_cost_per_1m=0.26),
                    speed=ModelLatency(
                        time_to_first_token_ms=50.0, tokens_per_second=100.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.6),
                ),
            ),
        ]

        with patch(
            "mcp_agent.tracing.token_counter.load_default_models",
            return_value=models,
        ):
            tc = TokenCounter()

            # Should match gpt-4o-mini-2024-07-18, not gpt-4o
            model = tc.find_model_info("gpt-4o-mini", "OpenAI")
            assert model is not None
            assert model.name == "gpt-4o-mini-2024-07-18"

            # Should match gpt-4o exactly
            model = tc.find_model_info("gpt-4o", "OpenAI")
            assert model is not None
            assert model.name == "gpt-4o"

    def test_case_insensitive_provider_lookup(self, token_counter):
        """Test that provider lookup is case-insensitive"""
        # Should find model even with different case
        model = token_counter.find_model_info("gpt-4", "openai")
        assert model is not None
        assert model.provider == "OpenAI"

        model = token_counter.find_model_info("claude-3-opus", "aws bedrock")
        assert model is not None
        assert model.provider == "AWS Bedrock"

    def test_blended_cost_calculation(self, token_counter):
        """Test cost calculation when only blended cost is available"""
        # Add a model with only blended cost
        models = [
            ModelInfo(
                name="test-model",
                provider="TestProvider",
                description="Test Model",
                context_window=128000,
                tool_calling=True,
                structured_outputs=True,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        blended_cost_per_1m=5.0,
                        input_cost_per_1m=None,
                        output_cost_per_1m=None,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=50.0, tokens_per_second=100.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.7),
                ),
            ),
        ]

        with patch(
            "mcp_agent.tracing.token_counter.load_default_models",
            return_value=models,
        ):
            tc = TokenCounter()

            # Should use blended cost when input/output costs are not available
            cost = tc.calculate_cost("test-model", 1000, 500, "TestProvider")
            expected = (1500 / 1_000_000) * 5.0
            assert cost == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_get_node_breakdown(self, token_counter):
        """Test getting detailed breakdown for a specific node"""
        await token_counter.push("app", "app")
        await token_counter.push("workflow", "workflow")
        await token_counter.push("agent1", "agent")
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await token_counter.pop()  # agent1

        await token_counter.push("agent2", "agent")
        await token_counter.record_usage(200, 100, "claude-3-opus", "Anthropic")
        await token_counter.pop()  # agent2

        # Get breakdown for workflow
        breakdown = await token_counter.get_node_breakdown("workflow", "workflow")

        assert breakdown is not None
        assert breakdown.name == "workflow"
        assert breakdown.node_type == "workflow"
        assert breakdown.direct_usage.total_tokens == 0  # workflow itself has no usage
        assert breakdown.usage.total_tokens == 450  # 150 + 300

        # Check children by type
        assert "agent" in breakdown.usage_by_node_type
        assert breakdown.usage_by_node_type["agent"].node_count == 2
        assert breakdown.usage_by_node_type["agent"].usage.total_tokens == 450

        # Check individual children
        assert len(breakdown.child_usage) == 2
        child_names = [child.name for child in breakdown.child_usage]
        assert "agent1" in child_names
        assert "agent2" in child_names

    @pytest.mark.asyncio
    async def test_get_models_breakdown(self, token_counter):
        """Test getting breakdown by model"""
        await token_counter.push("app", "app")
        await token_counter.push("agent1", "agent")
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await token_counter.pop()

        await token_counter.push("agent2", "agent")
        await token_counter.record_usage(200, 100, "gpt-4", "OpenAI")
        await token_counter.pop()

        await token_counter.push("agent3", "agent")
        await token_counter.record_usage(150, 75, "claude-3-opus", "Anthropic")
        await token_counter.pop()

        breakdown = await token_counter.get_models_breakdown()

        assert len(breakdown) == 2  # Two different models

        # Find GPT-4 breakdown
        gpt4_breakdown = next(b for b in breakdown if b.model_name == "gpt-4")
        assert gpt4_breakdown.total_tokens == 450  # 150 + 300
        assert gpt4_breakdown.input_tokens == 300  # 100 + 200
        assert gpt4_breakdown.output_tokens == 150  # 50 + 100
        assert len(gpt4_breakdown.nodes) == 2  # Two nodes used GPT-4

        # Find Claude breakdown
        claude_breakdown = next(b for b in breakdown if b.model_name == "claude-3-opus")
        assert claude_breakdown.total_tokens == 225
        assert len(claude_breakdown.nodes) == 1

    @pytest.mark.asyncio
    async def test_watch_basic(self, token_counter):
        """Test basic watch functionality"""
        await token_counter.push("app", "app")
        await token_counter.push("agent", "agent")

        # Track callback calls
        callback_calls = []

        async def callback(node, usage):
            callback_calls.append((node.name, usage.total_tokens))

        # Set up watch
        watch_id = await token_counter.watch(callback=callback, node_type="agent")

        # Record usage - should trigger callback
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")

        # Wait for async callback execution
        await asyncio.sleep(0.1)

        assert len(callback_calls) == 1
        assert callback_calls[0] == ("agent", 150)

        # Clean up
        assert await token_counter.unwatch(watch_id) is True

    @pytest.mark.asyncio
    async def test_watch_specific_node(self, token_counter):
        """Test watching a specific node"""
        await token_counter.push("app", "app")
        await token_counter.push("agent1", "agent")

        # Get the agent node
        agent_node = token_counter._current

        callback_calls = []

        async def callback(node, usage):
            callback_calls.append((node.name, usage.total_tokens))

        # Watch specific node
        watch_id = await token_counter.watch(callback=callback, node=agent_node)

        # Record usage on this node
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")

        # Pop and add another agent
        await token_counter.pop()
        await token_counter.push("agent2", "agent")

        # Record usage on different node - should NOT trigger
        await token_counter.record_usage(200, 100, "gpt-4", "OpenAI")

        # Wait for async execution
        await asyncio.sleep(0.1)

        # Should only have one callback from agent1
        assert len(callback_calls) == 1
        assert callback_calls[0] == ("agent1", 150)

        await token_counter.unwatch(watch_id)

    @pytest.mark.asyncio
    async def test_watch_threshold(self, token_counter):
        """Test watch with threshold"""
        await token_counter.push("app", "app")

        callback_calls = []

        async def callback(node, usage):
            callback_calls.append(usage.total_tokens)

        # Watch with threshold of 100 tokens
        watch_id = await token_counter.watch(
            callback=callback, node_type="app", threshold=100
        )

        # Record small usage - should NOT trigger
        await token_counter.record_usage(30, 20, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)
        assert len(callback_calls) == 0

        # Record more usage to exceed threshold - should trigger
        await token_counter.record_usage(40, 30, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)
        assert len(callback_calls) == 1
        assert callback_calls[0] == 120  # 50 + 70

        await token_counter.unwatch(watch_id)

    @pytest.mark.asyncio
    async def test_watch_throttling(self, token_counter):
        """Test watch with throttling"""
        await token_counter.push("app", "app")

        callback_calls = []

        async def callback(node, usage):
            callback_calls.append(time.time())

        # Watch with 100ms throttle
        watch_id = await token_counter.watch(
            callback=callback, node_type="app", throttle_ms=100
        )

        # Rapid updates
        for i in range(5):
            await token_counter.record_usage(10, 5, "gpt-4", "OpenAI")
            await asyncio.sleep(0.01)  # 10ms between updates

        # Wait for callbacks
        await asyncio.sleep(0.2)

        # Should have fewer callbacks than updates due to throttling
        assert len(callback_calls) < 5

        # Check that callbacks are at least 100ms apart
        if len(callback_calls) > 1:
            for i in range(1, len(callback_calls)):
                time_diff = (callback_calls[i] - callback_calls[i - 1]) * 1000
                assert time_diff >= 90  # Allow small timing variance

        await token_counter.unwatch(watch_id)

    @pytest.mark.asyncio
    async def test_watch_include_subtree(self, token_counter):
        """Test watch with include_subtree setting"""
        await token_counter.push("app", "app")
        await token_counter.push("workflow", "workflow")
        await token_counter.push("agent", "agent")

        app_node = await token_counter.find_node("app", "app")

        callback_calls = []

        async def callback(node, usage):
            callback_calls.append((node.name, usage.total_tokens))

        # Watch app node with include_subtree=True (default)
        watch_id = await token_counter.watch(callback=callback, node=app_node)

        # Record usage in agent - should trigger on app due to subtree
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)

        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "app"
        assert callback_calls[0][1] == 150

        # Now watch with include_subtree=False
        await token_counter.unwatch(watch_id)
        callback_calls.clear()

        watch_id = await token_counter.watch(
            callback=callback, node=app_node, include_subtree=False
        )

        # Record more usage in agent - should NOT trigger
        await token_counter.record_usage(50, 25, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)

        assert len(callback_calls) == 0

        await token_counter.unwatch(watch_id)

    @pytest.mark.asyncio
    async def test_watch_cache_invalidation(self, token_counter):
        """Test that cache invalidation works with watches"""
        await token_counter.push("app", "app")
        await token_counter.push("agent", "agent")

        # Get nodes
        app_node = await token_counter.find_node("app", "app")

        # Initial aggregation to populate cache
        initial_usage = app_node.aggregate_usage()
        assert app_node._cache_valid is True
        assert initial_usage.total_tokens == 0

        callback_calls = []

        async def callback(node, usage):
            # Check if cache was rebuilt (it should have been invalid before aggregate_usage)
            # The fact that we get correct usage means cache was properly invalidated and rebuilt
            callback_calls.append((node.name, usage.total_tokens))

        # Watch app node
        watch_id = await token_counter.watch(callback=callback, node=app_node)

        # Record usage - should invalidate cache and trigger watch
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")

        # Wait for callback
        await asyncio.sleep(0.1)

        # Callback should have correct aggregated value
        assert len(callback_calls) == 1
        assert callback_calls[0] == ("app", 150)

        # After the watch triggers, cache is re-validated by aggregate_usage()
        assert app_node._cache_valid is True
        assert app_node._cached_aggregate.total_tokens == 150

        # Record more usage
        await token_counter.record_usage(50, 25, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)

        # Should trigger again with updated value
        assert len(callback_calls) == 2
        assert callback_calls[1] == ("app", 225)

        await token_counter.unwatch(watch_id)

    @pytest.mark.asyncio
    async def test_multiple_watches(self, token_counter):
        """Test multiple watches on same node"""
        await token_counter.push("app", "app")

        callback1_calls = []
        callback2_calls = []

        async def callback1(_node, usage):
            callback1_calls.append(usage.total_tokens)

        async def callback2(_node, usage):
            callback2_calls.append(usage.total_tokens * 2)

        # Set up two watches
        watch_id1 = await token_counter.watch(callback=callback1, node_type="app")
        watch_id2 = await token_counter.watch(callback=callback2, node_type="app")

        # Record usage - should trigger both
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)

        assert len(callback1_calls) == 1
        assert callback1_calls[0] == 150
        assert len(callback2_calls) == 1
        assert callback2_calls[0] == 300

        # Remove one watch
        await token_counter.unwatch(watch_id1)

        # Record more usage
        await token_counter.record_usage(50, 25, "gpt-4", "OpenAI")
        await asyncio.sleep(0.1)

        # Only callback2 should be called
        assert len(callback1_calls) == 1  # No new calls
        assert len(callback2_calls) == 2
        assert callback2_calls[1] == 450  # (150 + 75) * 2

        await token_counter.unwatch(watch_id2)

    @pytest.mark.asyncio
    async def test_watch_cleanup_on_reset(self, token_counter):
        """Test that watches are cleaned up on reset"""
        await token_counter.push("app", "app")

        # Set up watch
        watch_id = await token_counter.watch(
            callback=lambda n, u: None, node_type="app"
        )

        assert len(token_counter._watches) == 1

        # Reset should clear watches
        await token_counter.reset()

        assert len(token_counter._watches) == 0
        assert len(token_counter._node_watches) == 0

        # Unwatch should return False for cleared watch
        assert await token_counter.unwatch(watch_id) is False

    @pytest.mark.asyncio
    async def test_get_agents_workflows_breakdown(self, token_counter):
        """Test getting breakdown by agent and workflow types"""
        await token_counter.push("app", "app")

        # Add workflow 1
        await token_counter.push("workflow1", "workflow")
        await token_counter.push("agent1", "agent")
        await token_counter.record_usage(100, 50, "gpt-4", "OpenAI")
        await token_counter.pop()
        await token_counter.pop()

        # Add workflow 2
        await token_counter.push("workflow2", "workflow")
        await token_counter.push("agent2", "agent")
        await token_counter.record_usage(200, 100, "claude-3-opus", "Anthropic")
        await token_counter.pop()
        await token_counter.pop()

        # Test agents breakdown
        agents = await token_counter.get_agents_breakdown()
        assert len(agents) == 2
        assert "agent1" in agents
        assert "agent2" in agents
        assert agents["agent1"].total_tokens == 150
        assert agents["agent2"].total_tokens == 300

        # Test workflows breakdown
        workflows = await token_counter.get_workflows_breakdown()
        assert len(workflows) == 2
        assert "workflow1" in workflows
        assert "workflow2" in workflows
        assert workflows["workflow1"].total_tokens == 150
        assert workflows["workflow2"].total_tokens == 300
