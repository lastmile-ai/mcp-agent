from unittest.mock import AsyncMock, MagicMock

from mcp import Tool
import pytest
from pydantic import BaseModel

from mcp.types import TextContent, SamplingMessage, ImageContent, ListToolsResult

from mcp_agent.config import BedrockSettings
from mcp_agent.workflows.llm.augmented_llm_bedrock import (
    BedrockAugmentedLLM,
    RequestParams,
    BedrockMCPTypeConverter,
    mcp_content_to_bedrock_content,
    bedrock_content_to_mcp_content,
    typed_dict_extras,
)


class TestBedrockAugmentedLLM:
    """
    Tests for the BedrockAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock Bedrock LLM instance with common mocks set up.
        """
        # Setup Bedrock-specific context attributes
        mock_context.config.bedrock = MagicMock()
        mock_context.config.bedrock = BedrockSettings(api_key="test_key")
        mock_context.config.bedrock.default_model = "us.amazon.nova-lite-v1:0"

        # Create LLM instance
        llm = BedrockAugmentedLLM(name="test", context=mock_context)

        # Apply common mocks
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="us.amazon.nova-lite-v1:0")
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        # Mock the Bedrock client
        llm.bedrock_client = MagicMock()
        llm.bedrock_client.converse = AsyncMock()

        return llm

    @staticmethod
    def create_text_response(text, stop_reason="end_turn", usage=None):
        """
        Creates a text response for testing.
        """
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": text}],
                },
            },
            "stopReason": stop_reason,
            "usage": usage
            or {
                "inputTokens": 150,
                "outputTokens": 100,
                "totalTokens": 250,
            },
        }

    @staticmethod
    def create_tool_use_response(
        tool_name, tool_args, tool_id, stop_reason="tool_use", usage=None
    ):
        """
        Creates a tool use response for testing.
        """
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "name": tool_name,
                                "input": tool_args,
                                "toolUseId": tool_id,
                            }
                        }
                    ],
                },
            },
            "stopReason": stop_reason,
            "usage": usage
            or {
                "inputTokens": 150,
                "outputTokens": 100,
                "totalTokens": 250,
            },
        }

    @staticmethod
    def create_tool_result_message(tool_result, tool_id, status="success"):
        """
        Creates a tool result message for testing.
        """
        return {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "content": tool_result,
                        "toolUseId": tool_id,
                        "status": status,
                    }
                }
            ],
        }

    @staticmethod
    def create_multiple_tool_use_response(
        tool_uses, text_prefix=None, stop_reason="tool_use", usage=None
    ):
        """
        Creates a response with multiple tool uses for testing.
        """
        content = []
        if text_prefix:
            content.append({"text": text_prefix})

        for tool_use in tool_uses:
            content.append(
                {
                    "toolUse": {
                        "name": tool_use["name"],
                        "input": tool_use.get("input", {}),
                        "toolUseId": tool_use["toolUseId"],
                    }
                }
            )

        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            },
            "stopReason": stop_reason,
            "usage": usage
            or {
                "inputTokens": 150,
                "outputTokens": 100,
                "totalTokens": 250,
            },
        }

    # Test 1: Basic Text Generation
    @pytest.mark.asyncio
    async def test_basic_text_generation(self, mock_llm):
        """
        Tests basic text generation without tools.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("This is a test response")
        )

        # Call LLM with default parameters
        responses = await mock_llm.generate("Test query")

        # Assertions
        assert len(responses) == 1
        assert responses[0]["content"][0]["text"] == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

        # Check the first call arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert first_call_args.payload["modelId"] == "us.amazon.nova-lite-v1:0"
        assert first_call_args.payload["messages"][0]["role"] == "user"
        assert (
            first_call_args.payload["messages"][0]["content"][0]["text"] == "Test query"
        )

    # Test 2: Generate String
    @pytest.mark.asyncio
    async def test_generate_str(self, mock_llm):
        """
        Tests the generate_str method which returns string output.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("This is a test response")
        )

        # Call LLM with default parameters
        response_text = await mock_llm.generate_str("Test query")

        # Assertions
        assert response_text == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

    # Test 3: Generate Structured Output
    @pytest.mark.asyncio
    async def test_generate_structured(self, mock_llm):
        """
        Tests structured output generation using Instructor.
        """

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Mock the generate_str method
        mock_llm.generate_str = AsyncMock(return_value="name: Test, value: 42")

        # Patch executor.execute to return the expected TestResponseModel instance
        mock_llm.executor.execute = AsyncMock(
            return_value=TestResponseModel(name="Test", value=42)
        )

        # Call the method
        result = await BedrockAugmentedLLM.generate_structured(
            mock_llm, "Test query", TestResponseModel
        )

        # Assertions
        assert isinstance(result, TestResponseModel)
        assert result.name == "Test"
        assert result.value == 42

    # Test 4: With History
    @pytest.mark.asyncio
    async def test_with_history(self, mock_llm):
        """
        Tests generation with message history.
        """
        # Setup history
        history_message = {"role": "user", "content": [{"text": "Previous message"}]}
        mock_llm.history.get = MagicMock(return_value=[history_message])

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Response with history")
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
        assert (
            first_call_args.payload["messages"][1]["content"][0]["text"]
            == "Follow-up query"
        )

    # Test 5: Without History
    @pytest.mark.asyncio
    async def test_without_history(self, mock_llm):
        """
        Tests generation without message history.
        """
        # Mock the history method to track if it gets called
        mock_history = MagicMock(
            return_value=[{"role": "user", "content": [{"text": "Ignored history"}]}]
        )
        mock_llm.history.get = mock_history

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Response without history")
        )

        # Call LLM with history disabled
        await mock_llm.generate("New query", RequestParams(use_history=False))

        # Assertions
        # Verify history.get() was not called since use_history=False
        mock_history.assert_not_called()

        # Check arguments passed to execute
        call_args = mock_llm.executor.execute.call_args[0][1]

        # Verify history not added to messages
        assert (
            len(
                [
                    m
                    for m in call_args.payload["messages"]
                    if m.get("content") == "Ignored history"
                ]
            )
            == 0
        )

    # Test 6: Tool Usage
    @pytest.mark.asyncio
    async def test_tool_usage(self, mock_llm: BedrockAugmentedLLM):
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
                    "test_tool", {"query": "test query"}, "tool_123"
                )
            # Second call is for the final response after tool call
            else:
                return self.create_text_response(
                    "Final response after tool use", stop_reason="end_turn"
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[TextContent(type="text", text="Tool result")], isError=False
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool")

        # Assertions
        assert len(responses) == 3
        assert "toolUse" in responses[0]["content"][0]
        assert responses[0]["content"][0]["toolUse"]["name"] == "test_tool"
        assert responses[1]["content"][0]["toolResult"]["toolUseId"] == "tool_123"
        assert responses[2]["content"][0]["text"] == "Final response after tool use"
        assert mock_llm.call_tool.call_count == 1

    # Test 7: Tool Error Handling
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_llm):
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
                    "test_tool", {"query": "test query"}, "tool_123"
                )
            # Second call is for the final response after tool call
            else:
                return self.create_text_response(
                    "Response after tool error", stop_reason="end_turn"
                )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[
                    TextContent(type="text", text="Tool execution failed with error")
                ],
                isError=True,
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool error")

        # Assertions
        assert len(responses) == 3
        assert "toolUse" in responses[0]["content"][0]
        assert responses[-1]["content"][0]["text"] == "Response after tool error"
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
    async def test_model_selection(self, mock_llm):
        """
        Tests model selection logic.
        """
        # Reset the mock to verify it's called
        mock_llm.select_model = AsyncMock(return_value="us.amazon.nova-v3:0")

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Model selection test")
        )

        # Call LLM with a specific model in request_params
        request_params = RequestParams(model="us.amazon.claude-v2:1")
        await mock_llm.generate("Test query", request_params)

        # Assertions
        assert mock_llm.select_model.call_count == 1
        # Verify the model parameter was passed (check the model name in request_params)
        assert mock_llm.select_model.call_args[0][0].model == "us.amazon.claude-v2:1"

    # Test 10: Request Parameters Merging
    @pytest.mark.asyncio
    async def test_request_params_merging(self, mock_llm):
        """
        Tests merging of request parameters with defaults.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Params test")
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
        Tests the BedrockMCPTypeConverter for converting between Bedrock and MCP types.
        """
        # Test conversion from Bedrock message to MCP result
        bedrock_message = {"role": "assistant", "content": [{"text": "Test content"}]}

        mcp_result = BedrockMCPTypeConverter.to_mcp_message_param(bedrock_message)
        assert mcp_result.role == "assistant"
        assert mcp_result.content.text == "Test content"

        # Test conversion from MCP message param to Bedrock message param
        mcp_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="Test MCP content")
        )
        bedrock_param = BedrockMCPTypeConverter.from_mcp_message_param(mcp_message)
        assert bedrock_param["role"] == "user"
        assert isinstance(bedrock_param["content"], list)
        assert bedrock_param["content"][0]["text"] == "Test MCP content"

    # Test 12: Content Block Conversions
    def test_content_block_conversions(self):
        """
        Tests conversion between MCP content formats and Bedrock content blocks.
        """
        # Test text content conversion
        text_content = [TextContent(type="text", text="Hello world")]
        bedrock_blocks = mcp_content_to_bedrock_content(text_content)
        assert len(bedrock_blocks) == 1
        assert bedrock_blocks[0]["text"] == "Hello world"

        # Convert back to MCP
        mcp_blocks = bedrock_content_to_mcp_content(bedrock_blocks)
        assert len(mcp_blocks) == 1
        assert isinstance(mcp_blocks[0], TextContent)
        assert mcp_blocks[0].text == "Hello world"

        # Test image content conversion
        image_content = [
            ImageContent(type="image", data="base64data", mimeType="image/png")
        ]
        bedrock_blocks = mcp_content_to_bedrock_content(image_content)
        assert len(bedrock_blocks) == 1
        assert bedrock_blocks[0]["image"]["source"] == "base64data"
        assert bedrock_blocks[0]["image"]["format"] == "image/png"

    # Test 13: Bedrock-Specific Stop Reasons
    @pytest.mark.asyncio
    async def test_stop_reasons(self, mock_llm):
        """
        Tests handling of different Bedrock stop reasons.
        """
        stop_reasons = [
            "end_turn",
            "stop_sequence",
            "max_tokens",
            "guardrail_intervened",
            "content_filtered",
        ]

        for stop_reason in stop_reasons:
            mock_llm.executor.execute = AsyncMock(
                return_value=self.create_text_response(
                    f"Response with {stop_reason}", stop_reason=stop_reason
                )
            )

            responses = await mock_llm.generate(f"Test query with {stop_reason}")

            assert len(responses) == 1
            assert responses[0]["content"][0]["text"] == f"Response with {stop_reason}"
            assert mock_llm.executor.execute.call_count == 1

            # Reset mock for next iteration
            mock_llm.executor.execute.reset_mock()

    # Test 14: Typed Dict Extras Helper
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

    # Test 15: Tool Configuration
    @pytest.mark.asyncio
    async def test_tool_configuration(self, mock_llm: BedrockAugmentedLLM):
        """
        Tests that tool configuration is properly set up.
        """
        # Setup agent to return tools
        mock_llm.agent.list_tools = AsyncMock(
            return_value=ListToolsResult(
                tools=[
                    Tool(
                        name="test_tool",
                        description="A test tool",
                        inputSchema={
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    )
                ]
            )
        )

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Tool config test")
        )

        # Call LLM
        await mock_llm.generate("Test query with tools")

        # Assertions
        call_kwargs = mock_llm.executor.execute.call_args[0][1]
        assert "toolConfig" in call_kwargs.payload
        assert len(call_kwargs.payload["toolConfig"]["tools"]) == 1
        assert (
            call_kwargs.payload["toolConfig"]["tools"][0]["toolSpec"]["name"]
            == "test_tool"
        )
        assert call_kwargs.payload["toolConfig"]["toolChoice"]["auto"] == {}

    # Test: Generate with String Input
    @pytest.mark.asyncio
    async def test_generate_with_string_input(self, mock_llm):
        """
        Tests generate() method with string input.
        """
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("String input response")
        )
        responses = await mock_llm.generate("This is a simple string message")
        assert len(responses) == 1
        assert responses[0]["content"][0]["text"] == "String input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["messages"][0]["role"] == "user"
        assert (
            req.payload["messages"][0]["content"][0]["text"]
            == "This is a simple string message"
        )

    # Test: Generate with MessageParamT Input
    @pytest.mark.asyncio
    async def test_generate_with_message_param_input(self, mock_llm):
        """
        Tests generate() method with MessageParamT input (Bedrock message dict).
        """
        message_param = {
            "role": "user",
            "content": [{"text": "This is a MessageParamT message"}],
        }
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("MessageParamT input response")
        )
        responses = await mock_llm.generate(message_param)
        assert len(responses) == 1
        assert responses[0]["content"][0]["text"] == "MessageParamT input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["messages"][0]["role"] == "user"
        assert (
            req.payload["messages"][0]["content"][0]["text"]
            == "This is a MessageParamT message"
        )

    # Test: Generate with PromptMessage Input
    @pytest.mark.asyncio
    async def test_generate_with_prompt_message_input(self, mock_llm):
        """
        Tests generate() method with PromptMessage input (MCP PromptMessage).
        """
        from mcp.types import PromptMessage, TextContent

        prompt_message = PromptMessage(
            role="user",
            content=TextContent(type="text", text="This is a PromptMessage"),
        )
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("PromptMessage input response")
        )
        responses = await mock_llm.generate(prompt_message)
        assert len(responses) == 1
        assert responses[0]["content"][0]["text"] == "PromptMessage input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["messages"][0]["role"] == "user"
        assert (
            req.payload["messages"][0]["content"][0]["text"]
            == "This is a PromptMessage"
        )

    # Test: Generate with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_with_mixed_message_types(self, mock_llm):
        """
        Tests generate() method with a list containing mixed message types.
        """
        from mcp.types import PromptMessage, TextContent

        messages = [
            "String message",
            {"role": "user", "content": [{"text": "MessageParamT response"}]},
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Mixed message types response")
        )
        responses = await mock_llm.generate(messages)
        assert len(responses) == 1
        assert responses[0]["content"][0]["text"] == "Mixed message types response"

    # Test: Generate String with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_str_with_mixed_message_types(self, mock_llm):
        """
        Tests generate_str() method with mixed message types.
        """
        from mcp.types import PromptMessage, TextContent

        messages = [
            "String message",
            {"role": "user", "content": [{"text": "MessageParamT response"}]},
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Mixed types string response")
        )
        response_text = await mock_llm.generate_str(messages)
        assert response_text == "Mixed types string response"

    # Test: Generate Structured with Mixed Message Types
    @pytest.mark.asyncio
    async def test_generate_structured_with_mixed_message_types(self, mock_llm):
        """
        Tests generate_structured() method with mixed message types.
        """
        from pydantic import BaseModel
        from mcp.types import PromptMessage, TextContent

        class TestResponseModel(BaseModel):
            name: str
            value: int

        messages = [
            "String message",
            {"role": "user", "content": [{"text": "MessageParamT response"}]},
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                '{"name": "MixedTypes", "value": 123}'
            )
        )
        # Patch generate_str to return the expected string
        mock_llm.generate_str = AsyncMock(
            return_value='{"name": "MixedTypes", "value": 123}'
        )
        # Patch executor.execute to return the expected model
        mock_llm.executor.execute = AsyncMock(
            return_value=TestResponseModel(name="MixedTypes", value=123)
        )
        result = await BedrockAugmentedLLM.generate_structured(
            mock_llm, messages, TestResponseModel
        )
        assert isinstance(result, TestResponseModel)
        assert result.name == "MixedTypes"
        assert result.value == 123

    # Test 16: Multiple Tool Usage
    @pytest.mark.asyncio
    async def test_multiple_tool_usage(self, mock_llm: BedrockAugmentedLLM):
        """
        Tests multiple tool uses in a single response.
        Verifies that all tool results are combined into a single message.
        """
        # Setup mock executor to return multiple tool uses, then final response
        mock_llm.executor.execute = AsyncMock(
            side_effect=[
                self.create_multiple_tool_use_response(
                    tool_uses=[
                        {"name": "test_tool", "input": {}, "toolUseId": "tool_1"},
                        {"name": "test_tool", "input": {}, "toolUseId": "tool_2"},
                    ],
                    text_prefix="Processing with multiple tools",
                ),
                self.create_text_response("Final response after both tools"),
            ]
        )

        # Mock tool calls
        mock_llm.call_tool = AsyncMock(
            side_effect=[
                MagicMock(
                    content=[TextContent(type="text", text="Tool 1 result")],
                    isError=False,
                ),
                MagicMock(
                    content=[TextContent(type="text", text="Tool 2 result")],
                    isError=False,
                ),
            ]
        )

        # Call LLM
        responses = await mock_llm.generate("Test multiple tools")

        # Assertions
        assert len(responses) == 3

        # First response: assistant with 2 tool uses
        assert responses[0]["role"] == "assistant"
        assert len(responses[0]["content"]) == 3  # text + 2 tool uses

        # Second response: single user message with both tool results
        assert responses[1]["role"] == "user"
        assert len(responses[1]["content"]) == 2  # 2 tool results combined
        assert responses[1]["content"][0]["toolResult"]["toolUseId"] == "tool_1"
        assert responses[1]["content"][1]["toolResult"]["toolUseId"] == "tool_2"

        # Third response: final assistant message
        assert responses[2]["content"][0]["text"] == "Final response after both tools"

        # Verify both tools were called
        assert mock_llm.call_tool.call_count == 2
