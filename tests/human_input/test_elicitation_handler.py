import pytest
from unittest.mock import AsyncMock, MagicMock
import mcp.types as types
from mcp_agent.executor.temporal.session_proxy import SessionProxy
from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse
from mcp_agent.human_input.elicitation_handler import (
    elicitation_input_callback,
    _create_elicitation_message,
    _handle_elicitation_response,
)


class TestElicitationHandler:
    """Test the elicitation-based human input handler."""

    def test_create_elicitation_message_basic(self):
        """Test basic message creation."""
        request = HumanInputRequest(prompt="Please enter your name")
        message = _create_elicitation_message(request)

        assert "Please enter your name" in message

    def test_create_elicitation_message_with_description(self):
        """Test message creation with description."""
        request = HumanInputRequest(
            prompt="Enter your name", description="We need your name for the booking"
        )
        message = _create_elicitation_message(request)

        assert "We need your name for the booking" in message
        assert "Enter your name" in message

    def test_create_elicitation_message_with_timeout(self):
        """Test message creation with timeout."""
        request = HumanInputRequest(prompt="Enter your name", timeout_seconds=30)
        message = _create_elicitation_message(request)

        assert "Enter your name" in message
        assert "Timeout" not in message
        assert "30" not in message

    def test_handle_elicitation_response_accept(self):
        """Test handling accept response."""
        request = HumanInputRequest(prompt="Test", request_id="test-123")
        result = types.ElicitResult(action="accept", content={"response": "John Doe"})

        response = _handle_elicitation_response(result, request)

        assert isinstance(response, HumanInputResponse)
        assert response.request_id == "test-123"
        assert response.response == "John Doe"

    def test_handle_elicitation_response_decline(self):
        """Test handling decline response."""
        request = HumanInputRequest(prompt="Test", request_id="test-123")
        result = types.ElicitResult(action="decline")

        response = _handle_elicitation_response(result, request)

        assert response.request_id == "test-123"
        assert response.response == "decline"

    def test_handle_elicitation_response_cancel(self):
        """Test handling cancel response."""
        request = HumanInputRequest(prompt="Test", request_id="test-123")
        result = types.ElicitResult(action="cancel")

        response = _handle_elicitation_response(result, request)

        assert response.request_id == "test-123"
        assert response.response == "cancel"

    @pytest.mark.asyncio
    async def test_elicitation_input_callback_success(self):
        """Test successful elicitation callback."""
        # Mock the context and session proxy
        mock_context = MagicMock()
        mock_session = AsyncMock(spec=SessionProxy)

        # Mock the elicit method to return a successful response
        mock_session.elicit.return_value = types.ElicitResult(
            action="accept", content={"response": "Test response"}
        )

        mock_context.upstream_session = mock_session

        # Mock get_current_context() to return our mock context
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "mcp_agent.core.context.get_current_context", lambda: mock_context
            )

            request = HumanInputRequest(
                prompt="Please enter something", request_id="test-123"
            )

            response = await elicitation_input_callback(request)

            assert isinstance(response, HumanInputResponse)
            assert response.request_id == "test-123"
            assert response.response == "Test response"

            # Verify the session proxy was called correctly
            mock_session.elicit.assert_called_once()
            call_args = mock_session.elicit.call_args
            assert "Please enter something" in call_args.kwargs["message"]
            assert call_args.kwargs["related_request_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_elicitation_input_callback_no_context(self):
        """Test callback when no context is available."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr("mcp_agent.core.context.get_current_context", lambda: None)

            request = HumanInputRequest(prompt="Test")

            with pytest.raises(RuntimeError, match="No context available"):
                await elicitation_input_callback(request)

    @pytest.mark.asyncio
    async def test_elicitation_input_callback_no_session(self):
        """Test callback when SessionProxy is not available."""
        mock_context = MagicMock()
        mock_context.upstream_session = None

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "mcp_agent.core.context.get_current_context", lambda: mock_context
            )

            request = HumanInputRequest(prompt="Test")

            with pytest.raises(RuntimeError, match="Session required for elicitation"):
                await elicitation_input_callback(request)

    @pytest.mark.asyncio
    async def test_elicitation_input_callback_elicit_failure(self):
        """Test callback when elicitation fails."""
        mock_context = MagicMock()
        mock_session = AsyncMock(spec=SessionProxy)

        # Mock the elicit method to raise an exception
        mock_session.elicit.side_effect = Exception("Elicitation failed")

        mock_context.upstream_session = mock_session

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "mcp_agent.core.context.get_current_context", lambda: mock_context
            )

            request = HumanInputRequest(prompt="Test")

            with pytest.raises(RuntimeError, match="Elicitation failed"):
                await elicitation_input_callback(request)
