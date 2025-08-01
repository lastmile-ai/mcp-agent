"""
Tests for Enhanced Error Handling in AdaptiveWorkflow
"""

import pytest
import asyncio
from unittest.mock import patch

from mcp_agent.workflows.adaptive.error_handler import (
    WorkflowErrorHandler,
    ErrorContext,
    ErrorSeverity,
    ErrorCategory,
)


class TestWorkflowErrorHandler:
    """Test the enhanced error handler functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create an error handler instance"""
        return WorkflowErrorHandler()

    def test_categorize_error(self, error_handler):
        """Test error categorization"""
        # LLM errors
        assert (
            error_handler.categorize_error(Exception("API rate limit exceeded"))
            == ErrorCategory.LLM_ERROR
        )
        assert (
            error_handler.categorize_error(Exception("Model timeout"))
            == ErrorCategory.LLM_ERROR
        )

        # Validation errors
        assert (
            error_handler.categorize_error(Exception("Validation failed"))
            == ErrorCategory.VALIDATION_ERROR
        )
        assert (
            error_handler.categorize_error(Exception("Invalid response format"))
            == ErrorCategory.VALIDATION_ERROR
        )

        # Resource errors
        assert (
            error_handler.categorize_error(Exception("Token budget exceeded"))
            == ErrorCategory.RESOURCE_ERROR
        )
        assert (
            error_handler.categorize_error(Exception("Cost limit reached"))
            == ErrorCategory.RESOURCE_ERROR
        )

        # Network errors
        assert (
            error_handler.categorize_error(Exception("Connection refused"))
            == ErrorCategory.NETWORK_ERROR
        )
        assert (
            error_handler.categorize_error(Exception("HTTP 503 error"))
            == ErrorCategory.NETWORK_ERROR
        )

        # Logic errors
        assert (
            error_handler.categorize_error(
                AttributeError("'NoneType' has no attribute 'x'")
            )
            == ErrorCategory.LOGIC_ERROR
        )
        assert (
            error_handler.categorize_error(KeyError("missing_key"))
            == ErrorCategory.LOGIC_ERROR
        )

        # Unknown errors
        assert (
            error_handler.categorize_error(Exception("Random error"))
            == ErrorCategory.UNKNOWN_ERROR
        )

    def test_determine_severity(self, error_handler):
        """Test severity determination"""
        # Critical errors
        assert (
            error_handler.determine_severity(SystemExit(), {}) == ErrorSeverity.CRITICAL
        )
        assert (
            error_handler.determine_severity(KeyboardInterrupt(), {})
            == ErrorSeverity.CRITICAL
        )
        assert (
            error_handler.determine_severity(Exception("Budget exceeded"), {})
            == ErrorSeverity.CRITICAL
        )

        # Medium severity for validation
        assert (
            error_handler.determine_severity(Exception("Validation error"), {})
            == ErrorSeverity.MEDIUM
        )

        # High severity for network errors
        assert (
            error_handler.determine_severity(Exception("Connection timeout"), {})
            == ErrorSeverity.HIGH
        )

        # High severity late in process
        assert (
            error_handler.determine_severity(Exception("Some error"), {"iteration": 10})
            == ErrorSeverity.HIGH
        )

        # Default medium severity
        assert (
            error_handler.determine_severity(Exception("Some error"), {"iteration": 2})
            == ErrorSeverity.MEDIUM
        )

    @pytest.mark.asyncio
    async def test_handle_error(self, error_handler):
        """Test comprehensive error handling"""
        error = ValueError("Test error message")
        context = {
            "iteration": 3,
            "subtask_name": "Research APIs",
            "agent_name": "APIResearcher",
        }

        with patch("mcp_agent.workflows.adaptive.error_handler.logger") as mock_logger:
            error_context = await error_handler.handle_error(
                error=error, workflow_stage="execution", context=context
            )

        # Check error context
        assert (
            isinstance(error_context.error_type, type)
            and error_context.error_type is ValueError
        )
        assert error_context.error_message == "Test error message"
        assert error_context.workflow_stage == "execution"
        assert error_context.iteration == 3
        assert error_context.subtask_name == "Research APIs"
        assert error_context.agent_name == "APIResearcher"
        assert error_context.category == ErrorCategory.UNKNOWN_ERROR
        assert error_context.severity == ErrorSeverity.MEDIUM

        # Check that error was logged
        mock_logger.warning.assert_called_once()

        # Check error tracking
        assert len(error_handler.error_history) == 1
        assert error_handler.error_counts[ErrorCategory.UNKNOWN_ERROR] == 1

    def test_get_recovery_suggestions(self, error_handler):
        """Test recovery suggestion generation"""
        # LLM error suggestions
        llm_error_context = ErrorContext(
            error_type=Exception,
            error_message="API error",
            traceback_str="",
            category=ErrorCategory.LLM_ERROR,
            severity=ErrorSeverity.HIGH,
        )

        suggestions = error_handler.get_recovery_suggestions(llm_error_context)
        assert "Retry with exponential backoff" in suggestions
        assert "Switch to a different model" in suggestions

        # Add context-specific suggestions
        planning_error_context = ErrorContext(
            error_type=Exception,
            error_message="Planning failed",
            traceback_str="",
            category=ErrorCategory.LOGIC_ERROR,
            workflow_stage="planning",
            severity=ErrorSeverity.MEDIUM,
        )

        suggestions = error_handler.get_recovery_suggestions(planning_error_context)
        assert "Simplify the objective or break it into phases" in suggestions

        # Test repeated errors get additional suggestions
        for i in range(4):
            error_handler.error_counts[ErrorCategory.LLM_ERROR] = i + 1

        suggestions = error_handler.get_recovery_suggestions(llm_error_context)
        assert "Consider restarting with different configuration" in suggestions

    def test_should_retry(self, error_handler):
        """Test retry decision logic"""
        # Don't retry critical errors
        critical_context = ErrorContext(
            error_type=Exception,
            error_message="Critical error",
            traceback_str="",
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.UNKNOWN_ERROR,
        )
        assert not error_handler.should_retry(critical_context)

        # Retry network errors up to 3 times
        network_context = ErrorContext(
            error_type=Exception,
            error_message="Network error",
            traceback_str="",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.NETWORK_ERROR,
        )

        assert error_handler.should_retry(network_context)

        # Don't retry after too many attempts
        error_handler.error_counts[ErrorCategory.NETWORK_ERROR] = 3
        assert not error_handler.should_retry(network_context)

        # Don't retry logic errors
        logic_context = ErrorContext(
            error_type=AttributeError,
            error_message="Logic error",
            traceback_str="",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.LOGIC_ERROR,
        )
        assert not error_handler.should_retry(logic_context)

    @pytest.mark.asyncio
    async def test_get_error_summary(self, error_handler):
        """Test error summary generation"""
        # Add some test errors
        await error_handler.handle_error(
            Exception("Error 1"), "planning", {"iteration": 1}
        )
        await error_handler.handle_error(
            Exception("API timeout"), "execution", {"iteration": 2}
        )
        await error_handler.handle_error(
            Exception("Validation failed"), "validation", {"iteration": 3}
        )

        summary = error_handler.get_error_summary()

        assert summary["total_errors"] == 3
        assert len(summary["by_category"]) > 0
        assert len(summary["by_severity"]) == len(ErrorSeverity)
        assert len(summary["recent_errors"]) == 3

        # Check recent error format
        recent = summary["recent_errors"][0]
        assert "timestamp" in recent
        assert "category" in recent
        assert "severity" in recent
        assert "message" in recent
        assert "stage" in recent

    @pytest.mark.asyncio
    async def test_create_debug_report(self, error_handler):
        """Test debug report generation"""
        # Add various errors
        for i in range(3):
            await error_handler.handle_error(
                Exception(f"Test error {i}"),
                f"stage_{i}",
                {"iteration": i, "subtask_name": f"Task {i}"},
            )

        # Test recovery attempt tracking
        if error_handler.error_history:
            error_handler.error_history[-1].recovery_attempted = True
            error_handler.error_history[-1].recovery_strategy = "Retry with backoff"

        report = error_handler.create_debug_report()

        # Check report structure
        assert "=== AdaptiveWorkflow Error Report ===" in report
        assert "Total errors: 3" in report
        assert "Error Summary by Category:" in report
        assert "Recent Errors (last 5):" in report
        assert "Recovery attempted: Retry with backoff" in report
        assert "=== End of Report ===" in report

    @pytest.mark.asyncio
    async def test_concurrent_error_handling(self, error_handler):
        """Test that error handler is thread-safe for tracking"""

        async def add_errors(name):
            for i in range(10):
                await error_handler.handle_error(
                    Exception(f"Concurrent error {i}"),
                    "concurrent_test",
                    {"coroutine": name},
                )

        # Create multiple coroutines
        tasks = []
        for i in range(5):
            task = add_errors(f"Coroutine-{i}")
            tasks.append(task)

        # Wait for all coroutines
        await asyncio.gather(*tasks)

        # Should have tracked all errors
        assert len(error_handler.error_history) == 50  # 5 coroutines * 10 errors

    def test_error_format_log(self, error_handler):
        """Test error log formatting"""
        error_context = ErrorContext(
            error_type=ValueError,
            error_message="Test validation error",
            traceback_str="Traceback...",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.VALIDATION_ERROR,
            workflow_stage="validation",
            iteration=5,
            subtask_name="ValidateResults",
        )

        log_msg = error_handler._format_error_log(error_context)

        assert "[HIGH]" in log_msg
        assert "validation_error:" in log_msg
        assert "Test validation error" in log_msg
        assert "at validation" in log_msg
        assert "(iteration 5)" in log_msg
        assert "in subtask 'ValidateResults'" in log_msg
