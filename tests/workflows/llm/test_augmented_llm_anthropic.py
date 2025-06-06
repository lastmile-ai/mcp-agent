from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from mcp_agent.config import AnthropicSettings

from mcp.types import TextContent, SamplingMessage, PromptMessage
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from mcp_agent.workflows.llm.augmented_llm_anthropic import (
    AnthropicAugmentedLLM,
    RequestParams,
    AnthropicMCPTypeConverter,
    mcp_content_to_anthropic_content,
    anthropic_content_to_mcp_content,
    mcp_stop_reason_to_anthropic_stop_reason,
    anthropic_stop_reason_to_mcp_stop_reason,
    typed_dict_extras,
)


class TestAnthropicAugmentedLLM:
    """
    Tests for the AnthropicAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self):
        """
        Creates a mock LLM instance with common mocks set up.
        """
        # Setup mock objects
        mock_context = MagicMock()
        mock_context.config.anthropic = AnthropicSettings(api_key="test_key")
        mock_context.config.default_model = "claude-3-7-sonnet-latest"

        # Create LLM instance
        llm = AnthropicAugmentedLLM(name="test", context=mock_context)

        # Setup common mocks
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="claude-3-7-sonnet-latest")
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        # Create executor mock
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock()

        return llm

    @pytest.fixture
    def default_usage(self):
        """
        Returns a default usage object for testing.
        """
        return Usage(
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            input_tokens=2789,
            output_tokens=89,
        )

    @staticmethod
    def create_tool_use_message(call_count, usage):
        """
        Creates a tool use message for testing.
        """
        return Message(
            role="assistant",
            content=[
                ToolUseBlock(
                    type="tool_use",
                    name="search_tool",
                    input={"query": "test query"},
                    id=f"tool_{call_count}",
                )
            ],
            model="claude-3-7-sonnet-latest",
            stop_reason="tool_use",
            id=f"resp_{call_count}",
            type="message",
            usage=usage,
        )

    @staticmethod
    def create_text_message(text, usage, role="assistant", stop_reason="end_turn"):
        """
        Creates a text message for testing.
        """
        return Message(
            role=role,
            content=[TextBlock(type="text", text=text)],
            model="claude-3-7-sonnet-latest",
            stop_reason=stop_reason,
            id="final_response",
            type="message",
            usage=usage,
        )

    @staticmethod
    def create_tool_result_message(result_text, tool_id, usage, is_error=False):
        """
        Creates a tool result message for testing.
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": [{"type": "text", "text": result_text}],
                    "is_error": is_error,
                }
            ],
        }

    @staticmethod
    def check_final_iteration_prompt_in_messages(messages):
        """
        Checks if there's a final iteration prompt in the given messages.
        """
        for msg in messages:
            if (
                msg.get("role") == "user"
                and isinstance(msg.get("content"), str)
                and "please stop using tools" in msg.get("content", "").lower()
            ):
                return True
        return False

    def create_tool_use_side_effect(self, max_iterations, default_usage):
        """
        Creates a side effect function for tool use testing.
        """
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            messages = kwargs.get("messages", [])
            has_final_iteration_prompt = self.check_final_iteration_prompt_in_messages(
                messages
            )

            # Return a final text message with stop_reason="end_turn" on the last iteration
            if call_count == max_iterations or has_final_iteration_prompt:
                return self.create_text_message(
                    "Here is my final answer based on all the tool results gathered so far...",
                    default_usage,
                    stop_reason="end_turn",
                )
            else:
                return self.create_tool_use_message(call_count, default_usage)

        return side_effect

    # Test 1: Basic Text Generation
    @pytest.mark.asyncio
    async def test_basic_text_generation(self, mock_llm, default_usage):
        """
        Tests basic text generation without tools.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "This is a test response", default_usage
            )
        )

        # Call LLM with default parameters
        responses = await mock_llm.generate("Test query")

        # Assertions
        assert len(responses) == 1
        assert responses[0].content[0].text == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

        # Check the arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert first_call_args.payload["model"] == "claude-3-7-sonnet-latest"
        assert first_call_args.payload["messages"][0]["role"] == "user"
        assert first_call_args.payload["messages"][0]["content"] == "Test query"

    # Test 2: Generate String
    @pytest.mark.asyncio
    async def test_generate_str(self, mock_llm, default_usage):
        """
        Tests the generate_str method which returns string output.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "This is a test response", default_usage
            )
        )

        # Call LLM with default parameters
        response_text = await mock_llm.generate_str("Test query")

        # Assertions
        assert response_text == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

    # Test 3: Generate Structured Output
    @pytest.mark.asyncio
    async def test_generate_structured(self, mock_llm, default_usage):
        """
        Tests structured output generation using Instructor.
        """

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Mock the generate_str method to return a string that will be parsed by the instructor mock
        mock_llm.generate_str = AsyncMock(return_value="name: Test, value: 42")

        # Patch executor.execute to return the expected TestResponseModel instance
        mock_llm.executor.execute = AsyncMock(
            return_value=TestResponseModel(name="Test", value=42)
        )

        # Call the method
        result = await AnthropicAugmentedLLM.generate_structured(
            mock_llm, "Test query", TestResponseModel
        )

        # Assertions
        assert isinstance(result, TestResponseModel)
        assert result.name == "Test"
        assert result.value == 42

    # Test 4: With History
    @pytest.mark.asyncio
    async def test_with_history(self, mock_llm, default_usage):
        """
        Tests generation with message history.
        """
        # Setup history
        history_message = {"role": "user", "content": "Previous message"}
        mock_llm.history.get = MagicMock(return_value=[history_message])

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "Response with history", default_usage
            )
        )

        # Call LLM with history enabled
        responses = await mock_llm.generate(
            "Follow-up query", RequestParams(use_history=True)
        )

        # Assertions
        assert len(responses) == 1

        # Verify history was included in the request
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert len(first_call_args.payload["messages"]) >= 2
        assert first_call_args.payload["messages"][0] == history_message
        assert first_call_args.payload["messages"][1]["content"] == "Follow-up query"

    # Test 5: Without History
    @pytest.mark.asyncio
    async def test_without_history(self, mock_llm, default_usage):
        """
        Tests generation without message history.
        """
        # Mock the history method to track if it gets called
        mock_history = MagicMock(
            return_value=[{"role": "user", "content": "Ignored history"}]
        )
        mock_llm.history.get = mock_history

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "Response without history", default_usage
            )
        )

        # Call LLM with history disabled
        await mock_llm.generate("New query", RequestParams(use_history=False))

        # Assertions
        # Verify history.get() was not called since use_history=False
        mock_history.assert_not_called()

        # Check arguments passed to execute
        call_args = mock_llm.executor.execute.call_args[0][1]

        # Verify history not included in messages
        assert (
            len(
                [
                    content
                    for content in call_args.payload["messages"]
                    if content == "Ignored history"
                ]
            )
            == 0
        )

    # Test 6: Tool Usage
    @pytest.mark.asyncio
    async def test_tool_usage(self, mock_llm, default_usage):
        """
        Tests tool usage in the LLM.
        """
        # Create a custom side effect function for execute
        call_count = 0

        async def custom_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First call - LLM generates a tool call
            if call_count == 1:
                return self.create_tool_use_message(1, default_usage)
            # Second call - LLM generates final response after tool call
            else:
                return self.create_text_message(
                    "Final response after tool use", default_usage
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[TextContent(type="text", text="Tool result")],
                isError=False,
                tool_call_id="tool_1",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool")

        # Assertions
        assert len(responses) == 2  # Tool use message and final response
        assert responses[0].content[0].type == "tool_use"
        assert responses[0].content[0].name == "search_tool"
        assert responses[1].content[0].text == "Final response after tool use"
        assert mock_llm.call_tool.call_count == 1

    # Test 7: Tool Error Handling
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_llm, default_usage):
        """
        Tests handling of errors from tool calls.
        """
        # Create a custom side effect function for execute
        call_count = 0

        async def custom_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First call - LLM generates a tool call
            if call_count == 1:
                return self.create_tool_use_message(1, default_usage)
            # Second call - LLM generates final response after tool call
            else:
                return self.create_text_message(
                    "Response after tool error", default_usage
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[
                    TextContent(type="text", text="Tool execution failed with error")
                ],
                isError=True,
                tool_call_id="tool_1",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool error")

        # Assertions
        assert len(responses) == 2  # Tool use message and final response
        assert responses[0].content[0].type == "tool_use"
        assert responses[1].content[0].text == "Response after tool error"
        assert mock_llm.call_tool.call_count == 1

    # Test 8: API Error Handling
    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_llm):
        """
        Tests handling of API errors.
        """
        # Setup mock executor to raise an exception
        mock_llm.executor.execute = AsyncMock(return_value=Exception("API Error"))

        # Call LLM
        responses = await mock_llm.generate("Test query with API error")

        # Assertions
        assert len(responses) == 0  # Should return empty list on error
        assert mock_llm.executor.execute.call_count == 1

    # Test 9: Model Selection
    @pytest.mark.asyncio
    async def test_model_selection(self, mock_llm, default_usage):
        """
        Tests model selection logic.
        """
        # Reset the mock to verify it's called
        mock_llm.select_model = AsyncMock(return_value="claude-3-8-haiku-latest")

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message("Model selection test", default_usage)
        )

        # Call LLM with a specific model in request_params
        request_params = RequestParams(model="claude-3-opus-latest")
        await mock_llm.generate("Test query", request_params)

        # Assertions
        assert mock_llm.select_model.call_count == 1
        # Verify the model parameter was passed
        assert mock_llm.select_model.call_args[0][0].model == "claude-3-opus-latest"

    # Test 10: Request Parameters Merging
    @pytest.mark.asyncio
    async def test_request_params_merging(self, mock_llm, default_usage):
        """
        Tests merging of request parameters with defaults.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message("Params test", default_usage)
        )

        # Create custom request params that override some defaults
        request_params = RequestParams(
            maxTokens=2000, temperature=0.8, max_iterations=5
        )

        # Call LLM with custom params
        await mock_llm.generate("Test query", request_params)

        # Get the merged params that were passed
        merged_params = mock_llm.get_request_params(request_params)

        # Assertions
        assert merged_params.maxTokens == 2000  # Our override
        assert merged_params.temperature == 0.8  # Our override
        assert merged_params.max_iterations == 5  # Our override
        # Should still have default model
        assert merged_params.model == mock_llm.default_request_params.model

    # Test 11: Type Conversion
    def test_type_conversion(self, default_usage):
        """
        Tests the AnthropicMCPTypeConverter for converting between Anthropic and MCP types.
        """
        # Test conversion from Anthropic message to MCP result
        anthropic_message = Message(
            role="assistant",
            content=[TextBlock(type="text", text="Test content")],
            model="claude-3-7-sonnet-latest",
            stop_reason="end_turn",
            id="test_id",
            type="message",
            usage=default_usage,
        )

        mcp_result = AnthropicMCPTypeConverter.to_mcp_message_result(anthropic_message)
        assert mcp_result.role == "assistant"
        assert mcp_result.content.text == "Test content"
        assert mcp_result.stopReason == "endTurn"
        assert mcp_result.id == "test_id"

        # Test conversion from MCP message param to Anthropic message param
        mcp_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="Test MCP content")
        )
        anthropic_param = AnthropicMCPTypeConverter.from_mcp_message_param(mcp_message)
        assert anthropic_param["role"] == "user"
        assert len(anthropic_param["content"]) == 1
        assert anthropic_param["content"][0]["type"] == "text"
        assert anthropic_param["content"][0]["text"] == "Test MCP content"

    # Test 12: Content Block Conversions
    def test_content_block_conversions(self):
        """
        Tests conversion between MCP content formats and Anthropic content blocks.
        """
        # Test text content conversion
        text_content = TextContent(type="text", text="Hello world")
        anthropic_content = mcp_content_to_anthropic_content(
            text_content, for_message_param=True
        )
        assert anthropic_content["type"] == "text"
        assert anthropic_content["text"] == "Hello world"

        # Convert back to MCP
        anthropic_content_list = [anthropic_content]
        mcp_blocks = anthropic_content_to_mcp_content(anthropic_content_list)
        assert len(mcp_blocks) == 1
        assert isinstance(mcp_blocks[0], TextContent)
        assert mcp_blocks[0].text == "Hello world"

    # Test 13: Stop Reason Conversion
    def test_stop_reason_conversion(self):
        """
        Tests conversion between MCP and Anthropic stop reasons.
        """
        # MCP to Anthropic
        assert mcp_stop_reason_to_anthropic_stop_reason("endTurn") == "end_turn"
        assert mcp_stop_reason_to_anthropic_stop_reason("maxTokens") == "max_tokens"
        assert (
            mcp_stop_reason_to_anthropic_stop_reason("stopSequence") == "stop_sequence"
        )
        assert mcp_stop_reason_to_anthropic_stop_reason("toolUse") == "tool_use"

        # Anthropic to MCP
        assert anthropic_stop_reason_to_mcp_stop_reason("end_turn") == "endTurn"
        assert anthropic_stop_reason_to_mcp_stop_reason("max_tokens") == "maxTokens"
        assert (
            anthropic_stop_reason_to_mcp_stop_reason("stop_sequence") == "stopSequence"
        )
        assert anthropic_stop_reason_to_mcp_stop_reason("tool_use") == "toolUse"

    # Test 14: System Prompt Handling
    @pytest.mark.asyncio
    async def test_system_prompt_handling(self, mock_llm, default_usage):
        """
        Tests system prompt is correctly passed to the API.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message("System prompt test", default_usage)
        )

        # Call LLM with a system prompt
        system_prompt = "You are a helpful assistant that speaks like a pirate."
        request_params = RequestParams(systemPrompt=system_prompt)
        await mock_llm.generate("Ahoy matey", request_params)

        # Assertions
        call_args = mock_llm.executor.execute.call_args[0][1]
        assert call_args.payload["system"] == system_prompt

    # Test 15: Typed Dict Extras Helper
    def test_typed_dict_extras(self):
        """
        Tests the typed_dict_extras helper function.
        """
        test_dict = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3",
        }

        # Exclude key1 and key3
        extras = typed_dict_extras(test_dict, ["key1", "key3"])
        assert "key1" not in extras
        assert "key3" not in extras
        assert extras["key2"] == "value2"

        # Exclude nothing
        extras = typed_dict_extras(test_dict, [])
        assert len(extras) == 3

        # Exclude everything
        extras = typed_dict_extras(test_dict, ["key1", "key2", "key3"])
        assert len(extras) == 0

    # Test 16: Max Iterations with Tool Use
    @pytest.mark.asyncio
    async def test_final_response_after_max_iterations_with_tool_use(
        self, mock_llm, default_usage
    ):
        """
        Tests whether we get a final text response when reaching max_iterations with tool_use.
        """
        # Setup executor with side effect
        mock_llm.executor.execute = AsyncMock(
            side_effect=self.create_tool_use_side_effect(3, default_usage)
        )

        # Setup tool call mock
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[TextContent(type="text", text="Tool result")],
                isError=False,
                tool_call_id="tool_1",
            )
        )

        # Call LLM with max_iterations=3
        request_params = RequestParams(
            model="claude-3-7-sonnet-latest",
            maxTokens=1000,
            max_iterations=3,
            use_history=True,
        )

        responses = await mock_llm.generate("Test query", request_params)

        # Assertions
        # 1. Verify the last response is a text response
        assert responses[-1].stop_reason == "end_turn"
        assert responses[-1].content[0].type == "text"
        assert "final answer" in responses[-1].content[0].text.lower()

        # 2. Verify execute was called the expected number of times
        assert mock_llm.executor.execute.call_count == request_params.max_iterations

        # 3. Verify final prompt was added before the last request
        calls = mock_llm.executor.execute.call_args_list
        final_call_args = calls[-1][0][1]  # Arguments of the last call
        messages = final_call_args.payload["messages"]

        # Check for the presence of the final answer request message
        assert self.check_final_iteration_prompt_in_messages(messages), (
            "No message requesting to stop using tools was found"
        )

    # Test 17: Generate with String Input
    @pytest.mark.asyncio
    async def test_generate_with_string_input(self, mock_llm, default_usage):
        """
        Tests generate() method with string input (Message type from Union).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "String input response", default_usage
            )
        )

        # Call LLM with string message
        responses = await mock_llm.generate("This is a simple string message")

        # Assertions
        assert len(responses) == 1
        assert responses[0].content[0].text == "String input response"

        # Check the arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert first_call_args.payload["messages"][0]["role"] == "user"
        assert (
            first_call_args.payload["messages"][0]["content"]
            == "This is a simple string message"
        )

    # Test 18: Generate with MessageParamT Input
    @pytest.mark.asyncio
    async def test_generate_with_message_param_input(self, mock_llm, default_usage):
        """
        Tests generate() method with MessageParamT input (Anthropic message dict).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "MessageParamT input response", default_usage
            )
        )

        # Create MessageParamT (Anthropic message dict)
        message_param = {"role": "user", "content": "This is a MessageParamT message"}

        # Call LLM with MessageParamT
        responses = await mock_llm.generate(message_param)

        # Assertions
        assert len(responses) == 1
        assert responses[0].content[0].text == "MessageParamT input response"

        # Check the arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert first_call_args.payload["messages"][0]["role"] == "user"
        assert (
            first_call_args.payload["messages"][0]["content"]
            == "This is a MessageParamT message"
        )

    # Test 19: Generate with PromptMessage Input
    @pytest.mark.asyncio
    async def test_generate_with_prompt_message_input(self, mock_llm, default_usage):
        """
        Tests generate() method with PromptMessage input (MCP PromptMessage).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "PromptMessage input response", default_usage
            )
        )

        # Create PromptMessage
        prompt_message = PromptMessage(
            role="user",
            content=TextContent(type="text", text="This is a PromptMessage"),
        )

        # Call LLM with PromptMessage
        responses = await mock_llm.generate(prompt_message)

        # Assertions
        assert len(responses) == 1
        assert responses[0].content[0].text == "PromptMessage input response"

    # Test 20: Generate with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate() method with a list containing mixed message types.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "Mixed message types response", default_usage
            )
        )

        # Create list with mixed message types
        messages = [
            "String message",  # str
            {"role": "assistant", "content": "MessageParamT response"},  # MessageParamT
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),  # PromptMessage
        ]

        # Call LLM with mixed message types
        responses = await mock_llm.generate(messages)

        # Assertions
        assert len(responses) == 1
        assert responses[0].content[0].text == "Mixed message types response"

    # Test 24: Generate String with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_str_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate_str() method with mixed message types.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_message(
                "Mixed types string response", default_usage
            )
        )

        # Create list with mixed message types
        messages = [
            "String message",
            {"role": "assistant", "content": "MessageParamT response"},
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]

        # Call generate_str with mixed message types
        response_text = await mock_llm.generate_str(messages)

        # Assertions
        assert response_text == "Mixed types string response"

    @pytest.mark.asyncio
    async def test_generate_structured_with_mixed_message_types(self, mock_llm):
        """
        Tests generate_structured() method with mixed message types.
        """

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Create list with mixed message types
        messages = [
            "String message",
            {"role": "assistant", "content": "MessageParamT response"},
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]

        mock_llm.generate_str = AsyncMock(return_value="name: MixedTypes, value: 123")
        # Patch executor.execute to return the expected TestResponseModel instance
        mock_llm.executor.execute = AsyncMock(
            return_value=TestResponseModel(name="MixedTypes", value=123)
        )

        # Call generate_structured with mixed message types
        result = await mock_llm.generate_structured(messages, TestResponseModel)

        # Assertions
        assert isinstance(result, TestResponseModel)
        assert result.name == "MixedTypes"
        assert result.value == 123
