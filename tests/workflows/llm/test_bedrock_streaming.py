"""Tests for Bedrock streaming implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_agent.config import BedrockSettings
from mcp_agent.workflows.llm.augmented_llm_bedrock import BedrockAugmentedLLM
from mcp_agent.workflows.llm.streaming_events import StreamEventType


class TestBedrockStreaming:
    """Tests for BedrockAugmentedLLM streaming functionality."""

    @pytest.fixture
    def mock_llm(self, mock_context):
        """Creates a mock LLM instance with common mocks set up."""
        mock_context.config.bedrock = BedrockSettings()

        llm = BedrockAugmentedLLM(name="test", context=mock_context)

        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(
            return_value="us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        return llm

    @staticmethod
    def create_mock_stream_response(events, usage=None):
        """Creates a mock Bedrock stream response."""
        if usage is None:
            usage = {"inputTokens": 100, "outputTokens": 50}

        # Append metadata event with usage (Bedrock sends this after messageStop)
        events_with_metadata = list(events) + [{"metadata": {"usage": usage}}]

        return {
            "stream": iter(events_with_metadata),
            "usage": usage,
        }

    @staticmethod
    def create_text_delta_event(text):
        """Creates a Bedrock text delta event."""
        return {"contentBlockDelta": {"delta": {"text": text}}}

    @staticmethod
    def create_message_stop_event(stop_reason="end_turn"):
        """Creates a Bedrock message stop event."""
        return {"messageStop": {"stopReason": stop_reason}}

    @staticmethod
    def create_content_block_start_event(tool_use=None):
        """Creates a Bedrock content block start event."""
        if tool_use:
            return {"contentBlockStart": {"start": {"toolUse": tool_use}}}
        return {"contentBlockStart": {"start": {}}}

    @staticmethod
    def create_content_block_stop_event():
        """Creates a Bedrock content block stop event."""
        return {"contentBlockStop": {}}

    @pytest.mark.asyncio
    async def test_single_turn_text_streaming(self, mock_llm):
        """Test single-turn text generation with streaming."""
        # Create mock streaming events
        text_deltas = ["Hello", " ", "world", "!"]
        mock_events = [self.create_text_delta_event(delta) for delta in text_deltas]
        mock_events.append(self.create_content_block_stop_event())
        mock_events.append(self.create_message_stop_event("end_turn"))

        mock_stream_response = self.create_mock_stream_response(mock_events)

        # Mock the bedrock client
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value

            mock_client = MagicMock()
            mock_session.client.return_value = mock_client

            # Mock converse_stream to return our mock response
            def mock_converse_stream(**kwargs):
                return mock_stream_response

            mock_client.converse_stream = mock_converse_stream

            # Collect events
            events = []
            async for event in mock_llm.generate_stream("Hello"):
                events.append(event)

        # Verify event sequence
        assert len(events) > 0

        # Check ITERATION_START event
        assert events[0].type == StreamEventType.ITERATION_START
        assert events[0].iteration == 0

        # Check TEXT_DELTA events
        text_delta_events = [e for e in events if e.type == StreamEventType.TEXT_DELTA]
        assert len(text_delta_events) == 4
        assert [e.content for e in text_delta_events if e.content is not None] == text_deltas

        # Check ITERATION_END event
        iteration_end_events = [
            e for e in events if e.type == StreamEventType.ITERATION_END
        ]
        assert len(iteration_end_events) == 1
        assert iteration_end_events[0].stop_reason == "end_turn"
        assert iteration_end_events[0].usage is not None
        assert iteration_end_events[0].usage.get("input_tokens") == 100
        assert iteration_end_events[0].usage.get("output_tokens") == 50

        # Check COMPLETE event
        complete_events = [e for e in events if e.type == StreamEventType.COMPLETE]
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    async def test_multi_iteration_with_tool_calls(self, mock_llm):
        """Test multi-iteration streaming with tool calls."""
        # First iteration: tool use
        tool_use_events = [
            self.create_content_block_start_event(
                {"name": "search", "toolUseId": "tool_1", "input": {"query": "test"}}
            ),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("tool_use"),
        ]

        # Second iteration: final text
        text_events = [
            self.create_text_delta_event("Based"),
            self.create_text_delta_event(" on search"),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("end_turn"),
        ]

        # Mock tool execution
        mock_tool_result = MagicMock()
        mock_tool_result.content = [MagicMock(text="tool result")]
        mock_tool_result.isError = False
        mock_llm.call_tool = AsyncMock(return_value=mock_tool_result)

        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self.create_mock_stream_response(tool_use_events)
            else:
                return self.create_mock_stream_response(text_events)

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value
            mock_client = MagicMock()
            mock_session.client.return_value = mock_client
            mock_client.converse_stream = mock_converse_stream

            # Collect events
            events = []
            async for event in mock_llm.generate_stream("Search for something"):
                events.append(event)

        # Verify we have multiple iterations
        iteration_start_events = [
            e for e in events if e.type == StreamEventType.ITERATION_START
        ]
        assert len(iteration_start_events) == 2

        # Check tool events
        tool_use_start_events = [
            e for e in events if e.type == StreamEventType.TOOL_USE_START
        ]
        assert len(tool_use_start_events) == 1
        assert tool_use_start_events[0].content is not None
        assert tool_use_start_events[0].content.get("name") == "search"

        tool_result_events = [
            e for e in events if e.type == StreamEventType.TOOL_RESULT
        ]
        assert len(tool_result_events) == 1

        tool_use_end_events = [
            e for e in events if e.type == StreamEventType.TOOL_USE_END
        ]
        assert len(tool_use_end_events) == 1

        # Check final completion
        complete_events = [e for e in events if e.type == StreamEventType.COMPLETE]
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    async def test_stop_reasons(self, mock_llm):
        """Test different stop reasons are handled correctly."""
        stop_reasons = ["end_turn", "stop_sequence", "max_tokens"]

        for stop_reason in stop_reasons:
            mock_events = [
                self.create_text_delta_event("Text"),
                self.create_content_block_stop_event(),
                self.create_message_stop_event(stop_reason),
            ]
            mock_stream_response = self.create_mock_stream_response(mock_events)

            with patch(
                "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session
                mock_client = MagicMock()
                mock_session.client.return_value = mock_client
                mock_client.converse_stream = lambda **kwargs: mock_stream_response

                events = []
                async for event in mock_llm.generate_stream("Test"):
                    events.append(event)

            # Check ITERATION_END has correct stop_reason
            iteration_end = [
                e for e in events if e.type == StreamEventType.ITERATION_END
            ][0]
            assert iteration_end.stop_reason == stop_reason

    @pytest.mark.asyncio
    async def test_message_assembly_from_chunks(self, mock_llm):
        """Test that text chunks are properly assembled into final message."""
        # Multiple text deltas that should be concatenated
        mock_events = [
            self.create_text_delta_event("First "),
            self.create_text_delta_event("second "),
            self.create_text_delta_event("third"),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("end_turn"),
        ]

        mock_stream_response = self.create_mock_stream_response(mock_events)

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value
            mock_client = MagicMock()
            mock_session.client.return_value = mock_client
            mock_client.converse_stream = lambda **kwargs: mock_stream_response

            events = []
            async for event in mock_llm.generate_stream("Test"):
                events.append(event)

        # All text deltas should be yielded individually
        text_deltas = [e for e in events if e.type == StreamEventType.TEXT_DELTA]
        assert len(text_deltas) == 3
        assert text_deltas[0].content is not None
        assert text_deltas[0].content == "First "
        assert text_deltas[1].content is not None
        assert text_deltas[1].content == "second "
        assert text_deltas[2].content is not None
        assert text_deltas[2].content == "third"

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_llm):
        """Test error handling in streaming."""
        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as mock_session_class:
            # Make the client raise an exception
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            mock_session.client.side_effect = Exception("Bedrock Error")

            events = []
            async for event in mock_llm.generate_stream("Test"):
                events.append(event)

        # Should have an ERROR event
        error_events = [e for e in events if e.type == StreamEventType.ERROR]
        assert len(error_events) == 1
        assert "Bedrock Error" in str(error_events[0].content)

    @pytest.mark.asyncio
    async def test_history_management(self, mock_llm):
        """Test that history is properly managed during streaming."""
        mock_events = [
            self.create_text_delta_event("Response"),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("end_turn"),
        ]
        mock_stream_response = self.create_mock_stream_response(mock_events)

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value
            mock_client = MagicMock()
            mock_session.client.return_value = mock_client
            mock_client.converse_stream = lambda **kwargs: mock_stream_response

            _ = list([e async for e in mock_llm.generate_stream("Test")])

        # Verify history.set was called
        assert mock_llm.history.set.called

    @pytest.mark.asyncio
    async def test_generate_str_stream_convenience_method(self, mock_llm):
        """Test the generate_str_stream convenience method."""
        text_deltas = ["Hello", " ", "world"]
        mock_events = [self.create_text_delta_event(delta) for delta in text_deltas]
        mock_events.append(self.create_content_block_stop_event())
        mock_events.append(self.create_message_stop_event("end_turn"))

        mock_stream_response = self.create_mock_stream_response(mock_events)

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value
            mock_client = MagicMock()
            mock_session.client.return_value = mock_client
            mock_client.converse_stream = lambda **kwargs: mock_stream_response

            text_chunks = []
            async for text in mock_llm.generate_str_stream("Test"):
                text_chunks.append(text)

        # Should only get text deltas, no other events
        assert text_chunks == text_deltas

    @pytest.mark.asyncio
    async def test_tool_result_formatting(self, mock_llm):
        """Test that tool results are properly formatted in Bedrock format."""
        # Tool use event
        tool_use_events = [
            self.create_content_block_start_event(
                {
                    "name": "calculator",
                    "toolUseId": "calc_1",
                    "input": {"operation": "add", "a": 1, "b": 2},
                }
            ),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("tool_use"),
        ]

        # Mock tool execution
        mock_tool_result = MagicMock()
        mock_tool_result.content = [MagicMock(text="3")]
        mock_tool_result.isError = False
        mock_llm.call_tool = AsyncMock(return_value=mock_tool_result)

        # Second iteration with text response
        text_events = [
            self.create_text_delta_event("The answer is 3"),
            self.create_content_block_stop_event(),
            self.create_message_stop_event("end_turn"),
        ]

        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self.create_mock_stream_response(tool_use_events)
            else:
                return self.create_mock_stream_response(text_events)

        with patch(
            "mcp_agent.workflows.llm.augmented_llm_bedrock.Session"
        ) as MockSession:
            mock_session = MockSession.return_value
            mock_client = MagicMock()
            mock_session.client.return_value = mock_client
            mock_client.converse_stream = mock_converse_stream

            events = []
            async for event in mock_llm.generate_stream("What is 1+2?"):
                events.append(event)

        # Verify tool result event has correct format
        tool_result_events = [
            e for e in events if e.type == StreamEventType.TOOL_RESULT
        ]
        assert len(tool_result_events) == 1
        assert tool_result_events[0].content is not None
        assert tool_result_events[0].content.get("is_error") is False
