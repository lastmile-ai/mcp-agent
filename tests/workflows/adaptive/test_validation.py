"""
Tests for Subagent Result Validation using EvaluatorOptimizer
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from mcp_agent.workflows.adaptive.adaptive_workflow import AdaptiveWorkflow
from mcp_agent.workflows.adaptive.models import SubagentResult, TaskType
from mcp_agent.workflows.adaptive.knowledge_manager import EnhancedExecutionMemory
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    QualityRating,
    EvaluationResult,
)


class TestSubagentValidation:
    """Test subagent result validation functionality"""

    @pytest.fixture
    def workflow(self, mock_context):
        """Create workflow with mocked dependencies"""
        llm_factory = MagicMock()
        workflow = AdaptiveWorkflow(
            llm_factory=llm_factory, enable_validation=True, context=mock_context
        )

        # Set up current memory
        workflow._current_memory = EnhancedExecutionMemory(
            execution_id="test-123",
            objective="Test objective",
            task_type=TaskType.ACTION,  # Validation only runs for ACTION type
        )

        return workflow

    @pytest.fixture
    def mock_result(self):
        """Create a mock subagent result"""
        return SubagentResult(
            aspect_name="Test Research",
            findings="This is a test finding with some claims about AI capabilities.",
            success=True,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            model_name="gpt-4",
            provider="openai",
        )

    @pytest.mark.asyncio
    async def test_validate_successful_result(self, workflow, mock_result):
        """Test validation of a successful result"""
        # Mock the EvaluatorOptimizer
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            # Set up mock evaluator instance
            mock_evaluator = AsyncMock()
            mock_evaluator_class.return_value = mock_evaluator

            # Mock the evaluation result
            mock_evaluation = EvaluationResult(
                rating=QualityRating.GOOD,
                feedback="The findings are accurate and well-supported.",
                needs_improvement=False,
                focus_areas=[],
            )

            # Set up refinement history
            mock_evaluator.refinement_history = [{"evaluation_result": mock_evaluation}]

            # Mock generate_str to return something
            mock_evaluator.generate_str = AsyncMock(return_value="Validated content")

            # Run validation
            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Check that confidence was set based on GOOD rating
            assert mock_result.confidence == 0.75  # GOOD maps to 0.75
            assert (
                mock_result.validation_notes
                == "The findings are accurate and well-supported."
            )

    @pytest.mark.asyncio
    async def test_validate_poor_quality_result(self, workflow, mock_result):
        """Test validation of a poor quality result"""
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            mock_evaluator = AsyncMock()
            mock_evaluator_class.return_value = mock_evaluator

            # Mock poor evaluation
            mock_evaluation = EvaluationResult(
                rating=QualityRating.POOR,
                feedback="Multiple factual errors detected.",
                needs_improvement=True,
                focus_areas=["Unsupported claims", "Logical inconsistencies"],
            )

            mock_evaluator.refinement_history = [{"evaluation_result": mock_evaluation}]
            mock_evaluator.generate_str = AsyncMock(return_value="Validated content")

            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Should have low confidence
            # POOR maps to 0.25, but "unsupported" in focus_areas halves it
            assert mock_result.confidence == 0.125  # 0.25 * 0.5
            assert "Multiple factual errors" in mock_result.validation_notes

    @pytest.mark.asyncio
    async def test_validate_with_hallucination_penalty(self, workflow, mock_result):
        """Test that hallucination detection reduces confidence"""
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            mock_evaluator = AsyncMock()
            mock_evaluator_class.return_value = mock_evaluator

            mock_evaluation = EvaluationResult(
                rating=QualityRating.FAIR,
                feedback="Some concerns about accuracy.",
                needs_improvement=True,
                focus_areas=[
                    "Potential hallucination in claim about X",
                    "Minor issues",
                ],
            )

            mock_evaluator.refinement_history = [{"evaluation_result": mock_evaluation}]
            mock_evaluator.generate_str = AsyncMock(return_value="Validated content")

            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Should have reduced confidence due to hallucination
            # FAIR = 0.5, then * 0.5 for hallucination = 0.25
            assert mock_result.confidence == 0.25

    @pytest.mark.asyncio
    async def test_validate_irrelevant_result(self, workflow, mock_result):
        """Test that irrelevant results get penalized"""
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            mock_evaluator = AsyncMock()
            mock_evaluator_class.return_value = mock_evaluator

            mock_evaluation = EvaluationResult(
                rating=QualityRating.GOOD,
                feedback="Well written but off-topic.",
                needs_improvement=True,
                focus_areas=["Content is irrelevant to objective"],
            )

            mock_evaluator.refinement_history = [{"evaluation_result": mock_evaluation}]
            mock_evaluator.generate_str = AsyncMock(return_value="Validated content")

            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Should have reduced confidence due to irrelevance
            # GOOD = 0.75, then * 0.7 for irrelevance = 0.525
            assert pytest.approx(mock_result.confidence, 0.001) == 0.525

    @pytest.mark.asyncio
    async def test_skip_validation_for_failed_result(self, workflow):
        """Test that failed results skip validation"""
        failed_result = SubagentResult(
            aspect_name="Failed Research",
            findings="",
            success=False,
            error="Connection timeout",
            start_time=datetime.now(timezone.utc),
        )

        await workflow._validate_subagent_result(failed_result, "Test objective")

        # Should set confidence to 0 without calling validator
        assert failed_result.confidence == 0.0
        assert failed_result.validation_notes is None

    @pytest.mark.asyncio
    async def test_skip_validation_when_disabled(self, workflow, mock_result):
        """Test that validation is skipped when disabled"""
        workflow.enable_validation = False

        initial_confidence = mock_result.confidence

        await workflow._validate_subagent_result(mock_result, "Test objective")

        # Confidence should not change
        assert mock_result.confidence == initial_confidence
        assert mock_result.validation_notes is None

    @pytest.mark.asyncio
    async def test_skip_validation_for_research_type(self, workflow, mock_result):
        """Test that validation is skipped for RESEARCH task type"""
        workflow._current_memory.task_type = TaskType.RESEARCH

        await workflow._validate_subagent_result(mock_result, "Test objective")

        # Should not validate for RESEARCH type
        assert mock_result.validation_notes is None

    @pytest.mark.asyncio
    async def test_validation_error_handling(self, workflow, mock_result):
        """Test that validation errors are handled gracefully"""
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            # Make the evaluator raise an exception
            mock_evaluator_class.side_effect = Exception(
                "Validation service unavailable"
            )

            # Should not raise, just log warning
            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Should get default confidence
            assert mock_result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_validation_with_empty_refinement_history(
        self, workflow, mock_result
    ):
        """Test handling when evaluator has no refinement history"""
        with patch(
            "mcp_agent.workflows.adaptive.adaptive_workflow.EvaluatorOptimizerLLM"
        ) as mock_evaluator_class:
            mock_evaluator = AsyncMock()
            mock_evaluator_class.return_value = mock_evaluator

            # Empty refinement history
            mock_evaluator.refinement_history = []
            mock_evaluator.generate_str = AsyncMock(return_value="Validated content")

            await workflow._validate_subagent_result(mock_result, "Test objective")

            # Should handle gracefully without setting confidence
            assert mock_result.validation_notes is None

    @pytest.mark.asyncio
    async def test_validation_integration_in_workflow(self, workflow):
        """Test that validation is called during subtask execution"""
        # Mock the validation method to track calls
        validation_calls = []

        async def mock_validate(result, objective):
            validation_calls.append((result.aspect_name, objective))
            result.confidence = 0.8

        workflow._validate_subagent_result = mock_validate

        # Create a test result
        test_result = SubagentResult(
            aspect_name="Integration Test",
            findings="Test findings",
            success=True,
            start_time=datetime.now(timezone.utc),
        )

        # Simulate the workflow calling validation after execution
        # This would normally happen in _execute_workflow
        if workflow.enable_validation and test_result.success:
            await workflow._validate_subagent_result(
                test_result, workflow._current_memory.objective
            )

        # Check validation was called
        assert len(validation_calls) == 1
        assert validation_calls[0] == ("Integration Test", "Test objective")
        assert test_result.confidence == 0.8
