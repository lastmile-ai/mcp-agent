"""
Tests for Context Window Management in AdaptiveWorkflow
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Optional

from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import SubagentResult
from mcp_agent.workflows.adaptive.knowledge_manager import (
    EnhancedExecutionMemory,
    KnowledgeItem,
    KnowledgeType,
)
from mcp_agent.tracing.token_counter import TokenUsage
from mcp_agent.workflows.llm.llm_selector import (
    ModelInfo,
    ModelMetrics,
    ModelCost,
    ModelLatency,
    ModelBenchmarks,
)


class MockTokenCounter:
    """Mock TokenCounter for testing"""

    def __init__(self):
        self.model_info = ModelInfo(
            name="gpt-4",
            provider="openai",
            context_window=128000,  # GPT-4 context window
            metrics=ModelMetrics(
                cost=ModelCost(
                    blended_cost_per_1m=10.0,
                    input_cost_per_1m=5.0,
                    output_cost_per_1m=15.0,
                ),
                speed=ModelLatency(
                    time_to_first_token_ms=100.0, tokens_per_second=50.0
                ),
                intelligence=ModelBenchmarks(quality_score=0.9),
            ),
        )

        self.workflow_usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model_name="gpt-4",
            model_info=self.model_info,
        )

    def get_workflow_usage(self, name: str) -> Optional[TokenUsage]:
        return self.workflow_usage

    def find_model_info(
        self, model_name: str, provider: Optional[str] = None
    ) -> Optional[ModelInfo]:
        if model_name == self.model_info.name:
            return self.model_info
        elif model_name == "gpt-4" and provider == "openai":
            # Return GPT-4 info for the test
            return ModelInfo(
                name="gpt-4",
                provider="openai",
                context_window=128000,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        blended_cost_per_1m=10.0,
                        input_cost_per_1m=5.0,
                        output_cost_per_1m=15.0,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=100.0, tokens_per_second=50.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.9),
                ),
            )
        elif model_name == "gpt-3.5-turbo" and provider == "openai":
            # Return GPT-3.5 info for the test
            return ModelInfo(
                name="gpt-3.5-turbo",
                provider="openai",
                context_window=16000,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        blended_cost_per_1m=2.0,
                        input_cost_per_1m=1.0,
                        output_cost_per_1m=3.0,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=50.0, tokens_per_second=100.0
                    ),
                    intelligence=ModelBenchmarks(quality_score=0.7),
                ),
            )
        return None


class TestContextWindowManagement:
    """Test context window management functionality"""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context with token counter"""
        context = MagicMock()
        context.token_counter = MockTokenCounter()
        return context

    @pytest.fixture
    def workflow(self, mock_context):
        """Create a workflow with mocked dependencies"""
        llm_factory = MagicMock()
        workflow = AdaptiveWorkflow(
            llm_factory=llm_factory, context=mock_context, token_budget=100000
        )

        # Set up current memory
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test-123", objective="Test objective"
        )

        # Add some test data
        for i in range(10):
            workflow._current_memory.knowledge_items.append(
                KnowledgeItem(
                    question=f"Question {i}",
                    answer=f"Answer {i}" * 100,  # Make it reasonably sized
                    confidence=0.8,
                    knowledge_type=KnowledgeType.FACT,
                    sources=[f"Source {i}"],
                    relevance_score=0.8 - i * 0.05,
                )
            )

        workflow._current_memory.subagent_results = [
            SubagentResult(
                aspect_name="Test Aspect",
                findings="Test findings",
                success=True,
                start_time=datetime.now(timezone.utc),
                model_name="gpt-4",
                provider="openai",
            )
        ]

        return workflow

    def test_get_model_context_window(self, workflow):
        """Test getting model context window"""
        # Test with explicit model
        window = workflow._get_model_context_window("gpt-4", "openai")
        assert window == 128000

        # Test with unknown model
        window = workflow._get_model_context_window("unknown-model")
        assert window is None

        # Test getting from memory
        window = workflow._get_model_context_window()
        assert window == 128000  # Should get from subagent results

    @pytest.mark.asyncio
    async def test_check_and_manage_context_window_no_trimming(self, workflow):
        """Test context window check when no trimming is needed"""
        # Set low token usage
        workflow.context.token_counter.workflow_usage.total_tokens = 50000

        initial_knowledge_count = len(workflow._current_memory.knowledge_items)

        await workflow._check_and_manage_context_window()

        # Should not trim anything
        assert len(workflow._current_memory.knowledge_items) == initial_knowledge_count

    @pytest.mark.asyncio
    async def test_check_and_manage_context_window_with_trimming(self, workflow):
        """Test context window check when trimming is needed"""
        # Set high token usage (75% of context window)
        workflow.context.token_counter.workflow_usage.total_tokens = 96000

        initial_knowledge_count = len(workflow._current_memory.knowledge_items)

        # Mock the trim function to track calls
        trim_called = False
        items_removed = 0

        async def mock_trim(self, target_tokens):
            nonlocal trim_called, items_removed
            trim_called = True
            # Remove 2 items
            if len(workflow._current_memory.knowledge_items) >= 2:
                workflow._current_memory.knowledge_items = (
                    workflow._current_memory.knowledge_items[2:]
                )
                items_removed = 2
                return 2, 1000
            return 0, 0

        # Use patch to mock the method at the class level
        with patch.object(
            type(workflow._current_memory), "trim_to_token_limit", mock_trim
        ):
            # Add some research history to test that trimming too
            workflow._current_memory.research_history = [
                ["Synthesis 1"],
                ["Synthesis 2"],
                ["Synthesis 3"],
            ]

            await workflow._check_and_manage_context_window()

            # Should have called trim
            assert trim_called
            assert items_removed == 2
            assert (
                len(workflow._current_memory.knowledge_items)
                == initial_knowledge_count - 2
            )

    @pytest.mark.asyncio
    async def test_check_and_manage_context_window_aggressive_trimming(self, workflow):
        """Test aggressive trimming when usage is very high"""
        # Set very high token usage (85% of context window)
        workflow.context.token_counter.workflow_usage.total_tokens = 108800

        # Add research history
        workflow._current_memory.research_history = [
            ["Synthesis 1"],
            ["Synthesis 2"],
            ["Synthesis 3"],
            ["Synthesis 4"],
        ]

        initial_history_count = len(workflow._current_memory.research_history)

        await workflow._check_and_manage_context_window()

        # Should trim research history too
        assert len(workflow._current_memory.research_history) < initial_history_count
        assert len(workflow._current_memory.research_history) == 2  # Keep only last 2

    @pytest.mark.asyncio
    async def test_context_check_without_token_counter(self, workflow):
        """Test that context check handles missing token counter gracefully"""
        workflow.context.token_counter = None

        # Should not raise exception
        await workflow._check_and_manage_context_window()

        # Knowledge items should remain unchanged
        assert len(workflow._current_memory.knowledge_items) == 10

    @pytest.mark.asyncio
    async def test_context_check_without_memory(self, workflow):
        """Test that context check handles missing memory gracefully"""
        workflow._current_memory = None

        # Should not raise exception
        await workflow._check_and_manage_context_window()

    @pytest.mark.asyncio
    async def test_different_model_buffers(self, workflow):
        """Test that different models get different buffer sizes"""
        # Add more model info
        workflow.context.token_counter.model_info = ModelInfo(
            name="gpt-3.5-turbo",
            provider="openai",
            context_window=16000,
            metrics=ModelMetrics(
                cost=ModelCost(
                    blended_cost_per_1m=2.0,
                    input_cost_per_1m=1.0,
                    output_cost_per_1m=3.0,
                ),
                speed=ModelLatency(
                    time_to_first_token_ms=50.0, tokens_per_second=100.0
                ),
                intelligence=ModelBenchmarks(quality_score=0.7),
            ),
        )

        # GPT-4 buffer (15% of 128k)
        buffer_gpt4 = workflow._get_context_buffer("gpt-4", "openai")
        assert buffer_gpt4 == int(128000 * 0.15)

        # GPT-3.5 buffer (15% of 16k)
        buffer_gpt35 = workflow._get_context_buffer("gpt-3.5-turbo", "openai")
        assert buffer_gpt35 == int(16000 * 0.15)

        # Default buffer for unknown model
        buffer_unknown = workflow._get_context_buffer("unknown-model")
        assert buffer_unknown == 10000  # Fallback value

    @pytest.mark.asyncio
    async def test_context_management_during_workflow(self, workflow):
        """Test that context management is called at appropriate times"""
        # Mock the check method to track calls
        check_calls = []

        async def mock_check():
            check_calls.append(True)

        workflow._check_and_manage_context_window = mock_check

        # Simulate planning research (should trigger check)
        with patch.object(workflow, "_build_context", return_value="context"):
            with patch.object(workflow, "llm_factory") as mock_factory:
                mock_llm = AsyncMock()
                mock_llm.generate_structured = AsyncMock()
                mock_factory.return_value = mock_llm

                # This should call context check
                from opentelemetry import trace

                span = MagicMock(spec=trace.Span)

                try:
                    await workflow._plan_research(span)
                except Exception:
                    pass  # We're just testing the check was called

        # Should have called context check
        assert len(check_calls) > 0
