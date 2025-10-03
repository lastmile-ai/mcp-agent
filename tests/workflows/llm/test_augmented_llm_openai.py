import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage
from openai.types.chat import (
    ChatCompletionMessageToolCall,
    ChatCompletion,
    ChatCompletionMessage,
)
from pydantic import BaseModel

from mcp.types import TextContent, SamplingMessage, PromptMessage

from mcp_agent.config import OpenAISettings
from mcp_agent.workflows.llm.augmented_llm_openai import (
    OpenAIAugmentedLLM,
    RequestParams,
    MCPOpenAITypeConverter,
)


class TestOpenAIAugmentedLLM:
    """
    Tests for the OpenAIAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock OpenAI LLM instance with common mocks set up.
        """
        # Setup OpenAI-specific context attributes using a real OpenAISettings instance
        mock_context.config.openai = OpenAISettings(
            api_key="test_key",
            default_model="gpt-4o",
            base_url="https://api.openai.com/v1",
            http_client=None,
            reasoning_effort="medium",
        )

        # Create LLM instance
        llm = OpenAIAugmentedLLM(name="test", context=mock_context)

        # Apply common mocks
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="gpt-4o")
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        return llm

    @pytest.fixture
    def default_usage(self):
        """
        Returns a default usage object for testing.
        """
        return CompletionUsage(
            completion_tokens=100,
            prompt_tokens=150,
            total_tokens=250,
        )

    @staticmethod
    def create_text_response(text, finish_reason="stop", usage=None):
        """
        Creates a text response for testing.
        """
        message = ChatCompletionMessage(
            role="assistant",
            content=text,
        )
        choice = Choice(
            finish_reason=finish_reason,
            index=0,
            message=message,
        )
        return ChatCompletion(
            id="chatcmpl-123",
            choices=[choice],
            created=1677858242,
            model="gpt-4o",
            object="chat.completion",
            usage=usage,
        )

    @staticmethod
    def create_tool_use_response(
        tool_name, tool_args, tool_id, finish_reason="tool_calls", usage=None
    ):
        """
        Creates a tool use response for testing.
        """
        message = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=[
                ChatCompletionMessageToolCall(
                    id=tool_id,
                    type="function",
                    function={
                        "name": tool_name,
                        "arguments": json.dumps(tool_args),
                    },
                )
            ],
        )
        choice = Choice(
            finish_reason=finish_reason,
            index=0,
            message=message,
        )
        return ChatCompletion(
            id="chatcmpl-123",
            choices=[choice],
            created=1677858242,
            model="gpt-4o",
            object="chat.completion",
            usage=usage,
        )

    # Test 1: Basic Text Generation
    @pytest.mark.asyncio
    async def test_basic_text_generation(self, mock_llm, default_usage):
        """
        Tests basic text generation without tools.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "This is a test response", usage=default_usage
            )
        )

        # Call LLM with default parameters
        responses = await mock_llm.generate("Test query")

        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

        # Check the first call arguments passed to execute (need to be careful with indexes because response gets added to messages)
        first_call_args = mock_llm.executor.execute.call_args_list[0][0]
        request_obj = first_call_args[1]
        assert request_obj.payload["model"] == "gpt-4o"
        assert request_obj.payload["messages"][0]["role"] == "user"
        assert request_obj.payload["messages"][0]["content"] == "Test query"

    # Test 2: Generate String
    @pytest.mark.asyncio
    async def test_generate_str(self, mock_llm, default_usage):
        """
        Tests the generate_str method which returns string output.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "This is a test response", usage=default_usage
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
        Tests structured output generation using native OpenAI API.
        """
        import json

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Create a proper ChatCompletion response with JSON content
        json_content = json.dumps({"name": "Test", "value": 42})
        completion_response = self.create_text_response(
            json_content, usage=default_usage
        )

        # Patch executor.execute to return the ChatCompletion with JSON
        mock_llm.executor.execute = AsyncMock(return_value=completion_response)

        # Call the method
        result = await mock_llm.generate_structured("Test query", TestResponseModel)

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
            return_value=self.create_text_response(
                "Response with history", usage=default_usage
            )
        )

        # Call LLM with history enabled
        responses = await mock_llm.generate(
            "Follow-up query", RequestParams(use_history=True)
        )

        # Assertions
        assert len(responses) == 1

        # Verify history was included in the request - use first call args
        first_call_args = mock_llm.executor.execute.call_args_list[0][0]
        request_obj = first_call_args[1]
        assert len(request_obj.payload["messages"]) >= 2
        assert request_obj.payload["messages"][0] == history_message
        assert request_obj.payload["messages"][1]["content"] == "Follow-up query"

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
            return_value=self.create_text_response(
                "Response without history", usage=default_usage
            )
        )

        # Call LLM with history disabled
        await mock_llm.generate("New query", RequestParams(use_history=False))

        # Assertions
        # Verify history.get() was not called since use_history=False
        mock_history.assert_not_called()

        # Check arguments passed to execute
        call_args = mock_llm.executor.execute.call_args[0]
        request_obj = call_args[1]
        # Verify only the user message was included (the new query), not any history
        user_messages = [
            m for m in request_obj.payload["messages"] if m.get("role") == "user"
        ]
        assert len(user_messages) == 1
        assert request_obj.payload["messages"][0]["content"] == "New query"

    # Test 6: Tool Usage - simplified to avoid StopAsyncIteration
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

            # First call is for the regular execute
            if call_count == 1:
                return self.create_tool_use_response(
                    "test_tool",
                    {"query": "test query"},
                    "tool_123",
                    usage=default_usage,
                )
            # Second call is for tool call execution
            elif call_count == 2:
                # This is the final response after tool use
                return self.create_text_response(
                    "Final response after tool use", usage=default_usage
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[TextContent(type="text", text="Tool result")],
                isError=False,
                tool_call_id="tool_123",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool")

        # Assertions
        assert len(responses) == 2
        assert responses[0].tool_calls is not None
        assert responses[0].tool_calls[0].function.name == "test_tool"
        assert responses[1].content == "Final response after tool use"

    # Test 7: Tool Error Handling - simplified to avoid StopAsyncIteration
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

            # First call is for the regular execute
            if call_count == 1:
                return self.create_tool_use_response(
                    "test_tool",
                    {"query": "test query"},
                    "tool_123",
                    usage=default_usage,
                )
            # Second call is for tool call execution - returns the final response
            elif call_count == 2:
                return self.create_text_response(
                    "Response after tool error", usage=default_usage
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[
                    TextContent(type="text", text="Tool execution failed with error")
                ],
                isError=True,
                tool_call_id="tool_123",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool error")

        # Assertions
        assert len(responses) == 2
        assert responses[1].content == "Response after tool error"

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
        mock_llm.select_model = AsyncMock(return_value="gpt-4o-mini")

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Model selection test", usage=default_usage
            )
        )

        # Call LLM with a specific model in request_params
        request_params = RequestParams(model="gpt-4o-custom")
        await mock_llm.generate("Test query", request_params)

        # Assertions
        assert mock_llm.select_model.call_count == 1
        # Verify the model parameter was passed (but don't require exact object equality)
        assert mock_llm.select_model.call_args[0][0].model == "gpt-4o-custom"

    # Test 10: Request Parameters Merging
    @pytest.mark.asyncio
    async def test_request_params_merging(self, mock_llm, default_usage):
        """
        Tests merging of request parameters with defaults.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Params test", usage=default_usage)
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
    def test_type_conversion(self):
        """
        Tests the MCPOpenAITypeConverter for converting between OpenAI and MCP types.
        """
        # Test conversion from OpenAI message to MCP result
        openai_message = ChatCompletionMessage(role="assistant", content="Test content")
        mcp_result = MCPOpenAITypeConverter.to_mcp_message_result(openai_message)
        assert mcp_result.role == "assistant"
        assert mcp_result.content.text == "Test content"

        # Test conversion from MCP message param to OpenAI message param
        mcp_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="Test MCP content")
        )
        openai_param = MCPOpenAITypeConverter.from_mcp_message_param(mcp_message)
        assert openai_param["role"] == "user"
        assert isinstance(openai_param["content"], list)
        assert openai_param["content"][0]["text"] == "Test MCP content"

    # Test: Generate with String Input
    @pytest.mark.asyncio
    async def test_generate_with_string_input(self, mock_llm, default_usage):
        """
        Tests generate() method with string input (Message type from Union).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "String input response", usage=default_usage
            )
        )

        # Call LLM with string message
        responses = await mock_llm.generate("This is a simple string message")

        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "String input response"

        # Check the arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args_list[0][0]
        request_obj = first_call_args[1]
        assert request_obj.payload["messages"][0]["role"] == "user"
        assert (
            request_obj.payload["messages"][0]["content"]
            == "This is a simple string message"
        )

    # Test: Generate with MessageParamT Input
    @pytest.mark.asyncio
    async def test_generate_with_message_param_input(self, mock_llm, default_usage):
        """
        Tests generate() method with MessageParamT input (OpenAI message dict).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "MessageParamT input response", usage=default_usage
            )
        )

        # Create MessageParamT (OpenAI message dict)
        message_param = {"role": "user", "content": "This is a MessageParamT message"}

        # Call LLM with MessageParamT
        responses = await mock_llm.generate(message_param)

        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "MessageParamT input response"

        # Check the arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args_list[0][0]
        request_obj = first_call_args[1]
        assert request_obj.payload["messages"][0]["role"] == "user"
        assert (
            request_obj.payload["messages"][0]["content"]
            == "This is a MessageParamT message"
        )

    # Test: Generate with PromptMessage Input
    @pytest.mark.asyncio
    async def test_generate_with_prompt_message_input(self, mock_llm, default_usage):
        """
        Tests generate() method with PromptMessage input (MCP PromptMessage).
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "PromptMessage input response", usage=default_usage
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
        assert responses[0].content == "PromptMessage input response"

    # Test: Generate with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate() method with a list containing mixed message types.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Mixed message types response", usage=default_usage
            )
        )

        # Create list with mixed message types
        messages = [
            "String message",  # str
            {"role": "assistant", "content": "MessageParamT response"},  # MessageParamT
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]

        # Call LLM with mixed message types
        responses = await mock_llm.generate(messages)

        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "Mixed message types response"

    # Test: Generate String with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_str_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate_str() method with mixed message types.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Mixed types string response", usage=default_usage
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

    # Test: Generate Structured with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_structured_with_mixed_message_types(self, mock_llm):
        """
        Tests generate_structured() method with mixed message types.
        """
        import json

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

        # Create a proper ChatCompletion response with JSON content
        json_content = json.dumps({"name": "MixedTypes", "value": 123})
        completion_response = self.create_text_response(
            json_content,
            usage=CompletionUsage(
                completion_tokens=100, prompt_tokens=150, total_tokens=250
            ),
        )

        # Patch executor.execute to return the ChatCompletion with JSON
        mock_llm.executor.execute = AsyncMock(return_value=completion_response)

        # Call generate_structured with mixed message types
        result = await mock_llm.generate_structured(messages, TestResponseModel)

        # Assertions
        assert isinstance(result, TestResponseModel)
        assert result.name == "MixedTypes"
        assert result.value == 123

    # Test: OpenAIAugmentedLLM with default_request_params set with a user
    @pytest.mark.asyncio
    async def test_default_request_params_with_user(self, mock_llm, default_usage):
        """
        Tests OpenAIAugmentedLLM with default_request_params set with a user.
        """
        # Set default_request_params with a user
        mock_llm.default_request_params.user = "test_user_id"

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Response with user in default_request_params", usage=default_usage
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with user")

        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "Response with user in default_request_params"
        # Check that the user field is present in the payload
        request_obj = mock_llm.executor.execute.call_args[0][1]
        assert request_obj.payload.get("user") == "test_user_id"

    # Test: OpenAIAugmentedLLM with user set in OpenAI config
    @pytest.mark.asyncio
    async def test_user_in_openai_config(self, mock_llm, default_usage):
        """
        Tests OpenAIAugmentedLLM with user set in the OpenAI config.
        """
        # Set user in OpenAI config after mock_llm is created
        mock_llm.context.config.openai.user = "config_user_id"
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Response with user in openai config", usage=default_usage
            )
        )
        # Call LLM
        responses = await mock_llm.generate("Test query with config user")
        # Assertions
        assert len(responses) == 1
        assert responses[0].content == "Response with user in openai config"
        # Check that the user field is present in the payload
        request_obj = mock_llm.executor.execute.call_args[0][1]
        assert request_obj.payload.get("user") == "config_user_id"
