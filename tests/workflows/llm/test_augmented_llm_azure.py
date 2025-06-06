import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.ai.inference.models import (
    ChatResponseMessage,
    UserMessage,
    ToolMessage,
    ChatCompletionsToolCall,
    FunctionCall,
    TextContentItem,
    ImageContentItem,
    ImageUrl,
    SystemMessage,
    AssistantMessage,
)
from pydantic import BaseModel

from mcp.types import (
    TextContent,
    ImageContent,
    EmbeddedResource,
    TextResourceContents,
    SamplingMessage,
    CallToolResult,
)

from mcp_agent.workflows.llm.augmented_llm_azure import (
    AzureAugmentedLLM,
    RequestParams,
    MCPAzureTypeConverter,
)


class TestAzureAugmentedLLM:
    """
    Tests for the AzureAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock Azure LLM instance with common mocks set up.
        """
        # Use a real AzureSettings object for config.azure to satisfy Pydantic validation
        from mcp_agent.config import AzureSettings

        azure_settings = AzureSettings(
            api_key="test_key",
            endpoint="https://test-endpoint.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini",
            default_model="gpt-4o-mini",
            api_version="2025-01-01-preview",
            credential_scopes=["https://cognitiveservices.azure.com/.default"],
        )
        mock_context.config.azure = azure_settings

        # Create LLM instance
        llm = AzureAugmentedLLM(name="test", context=mock_context)

        # Apply common mocks
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="gpt-4o-mini")
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        # Mock the Azure client
        llm.azure_client = MagicMock()
        llm.azure_client.complete = AsyncMock()

        # Mock executor.execute_many to return the tool results as expected
        llm.executor.execute_many = AsyncMock(
            side_effect=lambda tool_tasks: [  # tool_tasks is a list of coroutines
                ToolMessage(tool_call_id="tool_123", content="Tool result")
                if hasattr(task, "cr_code")
                or hasattr(task, "__await__")  # crude check for coroutine
                else task
                for task in tool_tasks
            ]
        )

        return llm

    @pytest.fixture
    def default_usage(self):
        """
        Returns a default usage object for testing.
        """
        return {
            "completion_tokens": 100,
            "prompt_tokens": 150,
            "total_tokens": 250,
        }

    @staticmethod
    def create_text_response(text, finish_reason="stop", usage=None):
        """
        Creates a text response for testing.
        """
        message = ChatResponseMessage(
            role="assistant",
            content=text,
        )

        response = MagicMock()
        response.choices = [
            MagicMock(message=message, finish_reason=finish_reason, index=0)
        ]
        response.id = "chatcmpl-123"
        response.created = 1677858242
        response.model = "gpt-4o-mini"
        response.usage = usage

        return response

    @staticmethod
    def create_tool_use_response(
        tool_name, tool_args, tool_id, finish_reason="tool_calls", usage=None
    ):
        """
        Creates a tool use response for testing.
        """
        function_call = FunctionCall(
            name=tool_name,
            arguments=json.dumps(tool_args),
        )

        tool_call = ChatCompletionsToolCall(
            id=tool_id,
            type="function",
            function=function_call,
        )

        message = ChatResponseMessage(
            role="assistant",
            content=None,
            tool_calls=[tool_call],
        )

        response = MagicMock()
        response.choices = [
            MagicMock(message=message, finish_reason=finish_reason, index=0)
        ]
        response.id = "chatcmpl-123"
        response.created = 1677858242
        response.model = "gpt-4o-mini"
        response.usage = usage

        return response

    # Test 1: Basic Text Generation
    @pytest.mark.asyncio
    async def test_basic_text_generation(
        self, mock_llm: AzureAugmentedLLM, default_usage
    ):
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

        # Check the first call arguments passed to execute
        req = mock_llm.executor.execute.call_args_list[0][0][1]
        assert req.payload["model"] == "gpt-4o-mini"
        assert isinstance(req.payload["messages"][0], UserMessage)
        assert req.payload["messages"][0].content == "Test query"

    # Test 2: Generate String
    @pytest.mark.asyncio
    async def test_generate_str(self, mock_llm: AzureAugmentedLLM, default_usage):
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
    async def test_generate_structured(
        self, mock_llm: AzureAugmentedLLM, default_usage
    ):
        """
        Tests structured output generation using Azure's JsonSchemaFormat.
        """

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Set up the mock for text generation
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                '{"name": "Test", "value": 42}', usage=default_usage
            )
        )

        # Call the method
        result = await mock_llm.generate_structured("Test query", TestResponseModel)

        # Assertions
        assert isinstance(result, TestResponseModel)
        assert result.name == "Test"
        assert result.value == 42

        # Verify metadata was set correctly
        req = mock_llm.executor.execute.call_args_list[0][0][1]
        assert "response_format" in req.payload
        assert req.payload["response_format"].name == "TestResponseModel"

    # Test 4: With History
    @pytest.mark.asyncio
    async def test_with_history(self, mock_llm: AzureAugmentedLLM, default_usage):
        """
        Tests generation with message history.
        """
        # Setup history
        history_message = UserMessage(content="Previous message")
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

        # Verify history was included in the request
        req = mock_llm.executor.execute.call_args_list[0][0][1]
        assert len(req.payload["messages"]) >= 2
        assert req.payload["messages"][0] == history_message
        assert isinstance(req.payload["messages"][1], UserMessage)
        assert req.payload["messages"][1].content == "Follow-up query"

    # Test 5: Without History
    @pytest.mark.asyncio
    async def test_without_history(self, mock_llm: AzureAugmentedLLM, default_usage):
        """
        Tests generation without message history.
        """
        # Mock the history method to track if it gets called
        mock_history = MagicMock(return_value=[UserMessage(content="Ignored history")])
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
        req = mock_llm.executor.execute.call_args[0][1]
        assert len(req.payload["messages"]) == 2
        assert req.payload["messages"][0].content == "New query"
        assert req.payload["messages"][1].content == "Response without history"

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

            # First call is for the regular execute (tool call request)
            if call_count == 1:
                # Return a mock ChatCompletions object with .choices[0].message having tool_calls
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(
                        message=self.create_tool_use_response(
                            "test_tool",
                            {"query": "test query"},
                            "tool_123",
                            usage=default_usage,
                        )
                        .choices[0]
                        .message,
                        finish_reason="tool_calls",
                        index=0,
                    )
                ]
                return mock_response
            # Third call is for the final response (normal message)
            else:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(
                        message=self.create_text_response(
                            "Final response after tool use", usage=default_usage
                        )
                        .choices[0]
                        .message,
                        finish_reason="stop",
                        index=0,
                    )
                ]
                return mock_response

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        # executor.execute_many is already set up in the fixture to return the tool result

        # Call LLM
        responses = await mock_llm.generate("Test query with tool")

        # Assertions
        assert len(responses) == 3
        assert hasattr(responses[0], "tool_calls")
        assert responses[0].tool_calls is not None
        assert responses[0].tool_calls[0].function.name == "test_tool"
        assert responses[1].tool_call_id == "tool_123"
        assert responses[2].content == "Final response after tool use"

    # Test 7: Tool Error Handling
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_llm, default_usage):
        """
        Tests handling of errors from tool calls.
        """
        # Setup mocks
        mock_llm.executor.execute = AsyncMock(
            side_effect=[
                self.create_tool_use_response(
                    "test_tool",
                    {"query": "test query"},
                    "tool_123",
                    usage=default_usage,
                ),
                self.create_text_response(
                    "Response after tool error", usage=default_usage
                ),
            ]
        )
        mock_llm.executor.execute_many = AsyncMock(
            return_value=[
                ToolMessage(
                    tool_call_id="tool_123",
                    content="Tool execution failed with error",
                )
            ]
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool error")

        # Assertions
        assert len(responses) == 3
        assert responses[-1].content == "Response after tool error"

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
        mock_llm.select_model = AsyncMock(return_value="gpt-4-turbo")

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Model selection test", usage=default_usage
            )
        )

        # Call LLM with a specific model in request_params
        request_params = RequestParams(model="gpt-4-custom")
        await mock_llm.generate("Test query", request_params)

        # Assertions
        assert mock_llm.select_model.call_count == 1
        # Verify the model parameter was passed
        assert mock_llm.select_model.call_args[0][0].model == "gpt-4-custom"

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
        Tests the MCPAzureTypeConverter for converting between Azure and MCP types.
        """
        # Test conversion from Azure message to MCP result
        azure_message = ChatResponseMessage(role="assistant", content="Test content")
        mcp_result = MCPAzureTypeConverter.to_mcp_message_result(azure_message)
        assert mcp_result.role == "assistant"
        assert mcp_result.content.text == "Test content"

        # Test conversion from MCP message param to Azure message param
        mcp_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="Test MCP content")
        )
        azure_param = MCPAzureTypeConverter.from_mcp_message_param(mcp_message)
        assert azure_param.role == "user"

        # Test content conversion
        if isinstance(azure_param.content, str):
            assert azure_param.content == "Test MCP content"
        else:
            assert isinstance(azure_param.content, list)
            assert len(azure_param.content) == 1
            assert isinstance(azure_param.content[0], TextContentItem)
            assert azure_param.content[0].text == "Test MCP content"

    # Test 12: Content Type Handling
    def test_content_type_handling(self):
        """
        Tests handling of different content types in messages.
        """
        # Test text content
        text_content = "Hello world"
        azure_message = ChatResponseMessage(role="assistant", content=text_content)
        converted = MCPAzureTypeConverter.to_mcp_message_result(azure_message)
        assert converted.content.text == text_content

        # Test content items list
        content_items = [
            TextContentItem(text="Hello"),
            TextContentItem(text="World"),
        ]
        message_with_items = UserMessage(content=content_items)
        message_str = AzureAugmentedLLM.message_param_str(None, message_with_items)
        assert "Hello" in message_str
        assert "World" in message_str

    # Test 15: Error on Missing Azure Configuration
    def test_missing_azure_config(self, mock_context):
        """
        Tests that an error is raised when Azure configuration is missing.
        """
        # Remove Azure config
        mock_context.config.azure = None

        # Assert that initialization raises ValueError
        with pytest.raises(ValueError) as excinfo:
            AzureAugmentedLLM(name="test", context=mock_context)

        assert "Azure configuration not found" in str(excinfo.value)

    # Test 16: Direct Testing of execute_tool_call
    @pytest.mark.asyncio
    async def test_execute_tool_call_direct(self, mock_llm):
        """
        Tests the execute_tool_call method directly.
        """
        # Create a tool call
        function_call = FunctionCall(
            name="test_tool",
            arguments=json.dumps({"param1": "value1"}),
        )
        tool_call = ChatCompletionsToolCall(
            id="tool_123",
            type="function",
            function=function_call,
        )

        # Mock call_tool to return a result
        tool_result = CallToolResult(
            isError=False,
            content=[TextContent(type="text", text="Tool executed successfully")],
        )
        mock_llm.call_tool = AsyncMock(return_value=tool_result)

        # Execute tool call
        result = await mock_llm.execute_tool_call(tool_call)

        # Assertions
        assert result is not None
        assert result.tool_call_id == "tool_123"
        assert result.content == "Tool executed successfully"
        mock_llm.call_tool.assert_called_once()
        call_args = mock_llm.call_tool.call_args[1]
        assert call_args["tool_call_id"] == "tool_123"
        assert call_args["request"].params.name == "test_tool"
        assert call_args["request"].params.arguments == {"param1": "value1"}

    # Test 17: Execute Tool Call with Invalid JSON
    @pytest.mark.asyncio
    async def test_execute_tool_call_invalid_json(self, mock_llm):
        """
        Tests execute_tool_call with invalid JSON arguments.
        """
        # Create a tool call with invalid JSON
        function_call = FunctionCall(
            name="test_tool",
            arguments="{'invalid': json}",  # This is not valid JSON
        )
        tool_call = ChatCompletionsToolCall(
            id="tool_123",
            type="function",
            function=function_call,
        )

        # Patch call_tool as an AsyncMock to track calls
        from unittest.mock import AsyncMock

        mock_llm.call_tool = AsyncMock()

        # Execute tool call
        result = await mock_llm.execute_tool_call(tool_call)

        # Assertions
        assert result is not None
        assert result.tool_call_id == "tool_123"
        assert "Invalid JSON" in result.content
        # call_tool should not be called due to JSON parsing error
        assert not mock_llm.call_tool.called

    # Test 18: Test message_str Method
    def test_message_str(self):
        """
        Tests the message_str method for different response types.
        """
        # Test with content
        message_with_content = ChatResponseMessage(
            role="assistant", content="This is a test message"
        )
        result = AzureAugmentedLLM.message_str(None, message_with_content)
        assert result == "This is a test message"

        # Test with None content
        tool_call = ChatCompletionsToolCall(
            id="tool_123",
            type="function",
            function=FunctionCall(name="test_tool", arguments="{}"),
        )
        message_without_content = ChatResponseMessage(
            role="assistant",
            content=None,
            tool_calls=[tool_call],
        )
        result = AzureAugmentedLLM.message_str(None, message_without_content)
        assert str(tool_call) in result
        assert "tool_calls" in result

    # Test 19: Test message_param_str Method with Various Content Types
    def test_message_param_str_with_various_content(self):
        """
        Tests the message_param_str method with various content types.
        """
        # Test with string content
        message_with_string = UserMessage(content="String content")
        result = AzureAugmentedLLM.message_param_str(None, message_with_string)
        assert result == "String content"

        # Test with text content items
        message_with_text_items = UserMessage(
            content=[
                TextContentItem(text="Text item 1"),
                TextContentItem(text="Text item 2"),
            ]
        )
        result = AzureAugmentedLLM.message_param_str(None, message_with_text_items)
        assert "Text item 1" in result
        assert "Text item 2" in result

        # Test with image content item
        image_url = ImageUrl(
            url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        message_with_image = UserMessage(
            content=[ImageContentItem(image_url=image_url)]
        )
        result = AzureAugmentedLLM.message_param_str(None, message_with_image)
        assert "Image url:" in result
        assert "data:image/png;base64" in result

        # Test with None content
        message_without_content = UserMessage(content=None)
        result = AzureAugmentedLLM.message_param_str(None, message_without_content)
        assert result == "{'role': 'user'}"

    # Test 20: Test Helper Function mcp_content_to_azure_content
    @pytest.mark.parametrize("str_only", [True, False])
    def test_mcp_content_to_azure_content(self, str_only):
        """
        Tests the mcp_content_to_azure_content helper function.
        """
        from mcp_agent.workflows.llm.augmented_llm_azure import (
            mcp_content_to_azure_content,
        )

        # Create test content
        text_content = TextContent(type="text", text="Test text")
        image_content = ImageContent(
            type="image",
            mimeType="image/png",
            data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        )
        # TextResourceContents requires a 'uri' field; provide a dummy value for testing
        text_resource = TextResourceContents(
            uri="resource://dummy", text="Resource text"
        )
        embedded_resource = EmbeddedResource(resource=text_resource, type="resource")

        # Test with single text content
        result = mcp_content_to_azure_content([text_content], str_only=str_only)

        if str_only:
            assert isinstance(result, str)
            assert "Test text" in result
        else:
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContentItem)
            assert result[0].text == "Test text"

        # Test with multiple content types
        result = mcp_content_to_azure_content(
            [text_content, image_content, embedded_resource], str_only=str_only
        )

        if str_only:
            assert isinstance(result, str)
            assert "Test text" in result
            assert "image/png" in result
            assert "Resource text" in result
        else:
            assert isinstance(result, list)
            assert len(result) == 3
            assert isinstance(result[0], TextContentItem)
            assert isinstance(result[1], ImageContentItem)
            assert isinstance(result[2], TextContentItem)

    # Test 21: Test Helper Function azure_content_to_mcp_content
    def test_azure_content_to_mcp_content(self):
        """
        Tests the azure_content_to_mcp_content helper function.
        """
        from mcp_agent.workflows.llm.augmented_llm_azure import (
            azure_content_to_mcp_content,
        )

        # Test with string content
        string_content = "Simple string content"
        result = azure_content_to_mcp_content(string_content)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].text == "Simple string content"

        # Test with content items list
        content_items = [
            TextContentItem(text="Text item"),
            ImageContentItem(
                image_url=ImageUrl(
                    url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            ),
        ]
        result = azure_content_to_mcp_content(content_items)
        assert len(result) == 2
        assert isinstance(result[0], TextContent)
        assert result[0].text == "Text item"
        assert isinstance(result[1], ImageContent)
        assert result[1].type == "image"
        assert result[1].mimeType == "image/png"

        # Test with None content
        result = azure_content_to_mcp_content(None)
        assert len(result) == 0

    # Test 22: Test Helper Function image_url_to_mime_and_base64
    def test_image_url_to_mime_and_base64(self):
        """
        Tests the image_url_to_mime_and_base64 helper function.
        """
        from mcp_agent.workflows.llm.augmented_llm_azure import (
            image_url_to_mime_and_base64,
        )

        # Valid image URL
        valid_url = ImageUrl(
            url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        mime_type, base64_data = image_url_to_mime_and_base64(valid_url)
        assert mime_type == "image/png"
        assert (
            base64_data
            == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )

        # Invalid image URL
        invalid_url = ImageUrl(url="invalid-data-url")
        with pytest.raises(ValueError) as excinfo:
            image_url_to_mime_and_base64(invalid_url)
        assert "Invalid image data URI" in str(excinfo.value)

    # Test 23: Test Helper Function typed_dict_extras
    def test_typed_dict_extras(self):
        """
        Tests the typed_dict_extras helper function.
        """
        from mcp_agent.workflows.llm.augmented_llm_azure import typed_dict_extras

        # Test with dict including excluded and non-excluded fields
        test_dict = {
            "field1": "value1",
            "field2": "value2",
            "exclude_me": "value3",
            "also_exclude": "value4",
        }

        result = typed_dict_extras(test_dict, ["exclude_me", "also_exclude"])
        assert "field1" in result
        assert "field2" in result
        assert "exclude_me" not in result
        assert "also_exclude" not in result
        assert result["field1"] == "value1"
        assert result["field2"] == "value2"

        # Test with empty dict
        result = typed_dict_extras({}, ["any_field"])
        assert result == {}

        # Test with no exclusions
        result = typed_dict_extras(test_dict, [])
        assert len(result) == 4
        assert "exclude_me" in result

    # Test 24: Comprehensive Type Converter Tests
    def test_type_converter_comprehensive(self):
        """
        Comprehensive tests for the MCPAzureTypeConverter.
        """
        # Test to_mcp_message_param with different roles
        # User message
        user_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="User content")
        )
        azure_user = MCPAzureTypeConverter.from_mcp_message_param(user_message)
        assert azure_user.role == "user"

        # Assistant message
        assistant_message = SamplingMessage(
            role="assistant", content=TextContent(type="text", text="Assistant content")
        )
        azure_assistant = MCPAzureTypeConverter.from_mcp_message_param(
            assistant_message
        )
        assert azure_assistant.role == "assistant"

        # Unsupported role
        with pytest.raises(ValueError) as excinfo:
            MCPAzureTypeConverter.from_mcp_message_param(
                SamplingMessage(
                    role="unsupported_role",
                    content=TextContent(type="text", text="content"),
                )
            )
        assert "Input should be 'user' or 'assistant'" in str(excinfo.value)

    # Test 25: Parallel Tool Calls
    @pytest.mark.asyncio
    async def test_parallel_tool_calls(self, mock_llm, default_usage):
        """
        Tests parallel tool calls where multiple tools are called in a single response.
        """
        # Create tool calls
        function_call1 = FunctionCall(
            name="tool1",
            arguments=json.dumps({"param": "value1"}),
        )
        function_call2 = FunctionCall(
            name="tool2",
            arguments=json.dumps({"param": "value2"}),
        )

        tool_call1 = ChatCompletionsToolCall(
            id="call_1",
            type="function",
            function=function_call1,
        )
        tool_call2 = ChatCompletionsToolCall(
            id="call_2",
            type="function",
            function=function_call2,
        )

        # Create response with multiple tool calls
        message = ChatResponseMessage(
            role="assistant",
            content=None,
            tool_calls=[tool_call1, tool_call2],
        )

        response = MagicMock()
        response.choices = [
            MagicMock(message=message, finish_reason="tool_calls", index=0)
        ]
        response.id = "chatcmpl-123"
        response.created = 1677858242
        response.model = "gpt-4o-mini"
        response.usage = default_usage

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(
            side_effect=[
                response,
                self.create_text_response(
                    "Final response after parallel tools", usage=default_usage
                ),
            ]
        )
        mock_llm.executor.execute_many = AsyncMock(
            return_value=[
                ToolMessage(tool_call_id="call_1", content="Tool 1 result"),
                ToolMessage(tool_call_id="call_2", content="Tool 2 result"),
            ]
        )

        # Enable parallel tool calls
        request_params = RequestParams(parallel_tool_calls=True)

        # Call LLM
        responses = await mock_llm.generate("Test parallel tools", request_params)

        # Assertions
        assert len(responses) >= 3  # Initial response, tool results, final response
        assert hasattr(responses[0], "tool_calls")
        assert len(responses[0].tool_calls) == 2
        assert "tool1" in [tc.function.name for tc in responses[0].tool_calls]
        assert "tool2" in [tc.function.name for tc in responses[0].tool_calls]

    # Test 26: Multiple Iterations with Tool Calls
    @pytest.mark.asyncio
    async def test_multiple_iterations(self, mock_llm, default_usage):
        """
        Tests multiple iterations of generate with multiple tool calls.
        """
        # Setup mocks for multiple iterations
        mock_llm.executor.execute = AsyncMock(
            side_effect=[
                self.create_tool_use_response(
                    "tool_iter1",
                    {"query": "data1"},
                    "tool_id1",
                    usage=default_usage,
                ),
                self.create_tool_use_response(
                    "tool_iter2",
                    {"query": "data2"},
                    "tool_id2",
                    usage=default_usage,
                ),
                self.create_text_response(
                    "Final response after multiple iterations", usage=default_usage
                ),
            ]
        )
        mock_llm.executor.execute_many = AsyncMock(
            side_effect=[
                [
                    ToolMessage(
                        tool_call_id="tool_id1",
                        content="Result from first tool",
                    )
                ],
                [
                    ToolMessage(
                        tool_call_id="tool_id2",
                        content="Result from second tool",
                    )
                ],
            ]
        )

        # Set a high max_iterations to allow multiple iterations
        request_params = RequestParams(max_iterations=5)

        # Call LLM
        responses = await mock_llm.generate("Test multiple iterations", request_params)

        # Assertions
        assert len(responses) > 4  # Should have multiple responses
        assert mock_llm.executor.execute.call_count == 3

        # Verify the sequence of responses
        tool_call_responses = [
            r for r in responses if hasattr(r, "tool_calls") and r.tool_calls
        ]
        tool_result_responses = [r for r in responses if hasattr(r, "tool_call_id")]
        text_responses = [r for r in responses if hasattr(r, "content") and r.content]

        assert len(tool_call_responses) == 2  # Two tool call requests
        assert len(tool_result_responses) == 2  # Two tool results
        assert len(text_responses) >= 2  # At least interim and final responses

        # Verify final response
        assert "Final response" in responses[-1].content

    # Test 27: System Prompt Handling
    @pytest.mark.asyncio
    async def test_system_prompt_handling(self, mock_llm, default_usage):
        """
        Tests handling of system prompts in generate requests.
        """
        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Response with system prompt", usage=default_usage
            )
        )

        # Set system prompt in instance
        test_prompt = "This is a test system prompt"
        mock_llm.instruction = test_prompt

        # Call with empty history to ensure system prompt is included
        mock_llm.history.get = MagicMock(return_value=[])

        # Call LLM
        await mock_llm.generate("Test query")

        # Assertions
        req = mock_llm.executor.execute.call_args_list[0][0][1]
        messages = req.payload["messages"]

        # First message should be system message with our prompt
        assert len(messages) >= 2
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == test_prompt

        # Test with system prompt in request params
        request_prompt = "Override system prompt"
        request_params = RequestParams(systemPrompt=request_prompt)

        # Reset mock to clear call history
        mock_llm.executor.execute.reset_mock()

        # Call with request params
        await mock_llm.generate("Test query", request_params)

        # Assertions
        req = mock_llm.executor.execute.call_args_list[0][0][1]
        messages = req.payload["messages"]

        # Still should use instance instruction over request params
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == test_prompt

    # Test 28: Error in Tool Execution
    @pytest.mark.asyncio
    async def test_execute_tool_call_exception(self, mock_llm):
        """
        Tests execute_tool_call with an exception during tool call.
        """
        # Create a tool call
        function_call = FunctionCall(
            name="failing_tool",
            arguments=json.dumps({"param": "value"}),
        )
        tool_call = ChatCompletionsToolCall(
            id="tool_123",
            type="function",
            function=function_call,
        )

        # Mock call_tool to raise an exception
        mock_llm.call_tool = AsyncMock(side_effect=Exception("Tool execution failed"))

        # Execute tool call
        result = await mock_llm.execute_tool_call(tool_call)

        # Assertions
        assert result is not None
        assert result.tool_call_id == "tool_123"
        assert "Error executing tool" in result.content
        assert "Tool execution failed" in result.content

    # Test 29: convert_message_to_message_param Method
    def test_convert_message_to_message_param(self):
        """
        Tests the convert_message_to_message_param method.
        """
        # Create a response message
        response_message = ChatResponseMessage(
            role="assistant",
            content="Test response content",
            tool_calls=[
                ChatCompletionsToolCall(
                    id="tool_123",
                    type="function",
                    function=FunctionCall(name="test_tool", arguments="{}"),
                )
            ],
        )

        # Convert to message param
        param_message = AzureAugmentedLLM.convert_message_to_message_param(
            response_message
        )

        # Assertions
        assert isinstance(param_message, AssistantMessage)
        assert param_message.content == "Test response content"
        assert param_message.tool_calls is not None
        assert len(param_message.tool_calls) == 1
        assert param_message.tool_calls[0].function.name == "test_tool"

    # Test: Generate with String Input
    @pytest.mark.asyncio
    async def test_generate_with_string_input(self, mock_llm, default_usage):
        """
        Tests generate() method with string input.
        """
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "String input response", usage=default_usage
            )
        )
        responses = await mock_llm.generate("This is a simple string message")
        assert len(responses) == 1
        assert responses[0].content == "String input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert isinstance(req.payload["messages"][0], UserMessage)
        assert req.payload["messages"][0].content == "This is a simple string message"

    # Test: Generate with MessageParamT Input
    @pytest.mark.asyncio
    async def test_generate_with_message_param_input(self, mock_llm, default_usage):
        """
        Tests generate() method with MessageParamT input (Azure message dict).
        """
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "MessageParamT input response", usage=default_usage
            )
        )
        # Create MessageParamT (Azure message dict)
        message_param = UserMessage(content="This is a MessageParamT message")
        responses = await mock_llm.generate(message_param)
        assert len(responses) == 1
        assert responses[0].content == "MessageParamT input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert isinstance(req.payload["messages"][0], UserMessage)
        assert req.payload["messages"][0].content == "This is a MessageParamT message"

    # Test: Generate with PromptMessage Input
    @pytest.mark.asyncio
    async def test_generate_with_prompt_message_input(self, mock_llm, default_usage):
        """
        Tests generate() method with PromptMessage input (MCP PromptMessage).
        """
        from mcp.types import PromptMessage, TextContent

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "PromptMessage input response", usage=default_usage
            )
        )
        prompt_message = PromptMessage(
            role="user",
            content=TextContent(type="text", text="This is a PromptMessage"),
        )
        responses = await mock_llm.generate(prompt_message)
        assert len(responses) == 1
        assert responses[0].content == "PromptMessage input response"
        req = mock_llm.executor.execute.call_args[0][1]
        # Should be converted to UserMessage
        assert isinstance(req.payload["messages"][0], UserMessage)
        assert req.payload["messages"][0].content[0].text == "This is a PromptMessage"

    # Test: Generate with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate() method with a list containing mixed message types.
        """
        from mcp.types import PromptMessage, TextContent

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Mixed message types response", usage=default_usage
            )
        )
        messages = [
            "String message",
            UserMessage(content="MessageParamT response"),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        responses = await mock_llm.generate(messages)
        assert len(responses) == 1
        assert responses[0].content == "Mixed message types response"

    # Test: Generate String with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_str_with_mixed_message_types(self, mock_llm, default_usage):
        """
        Tests generate_str() method with mixed message types.
        """
        from mcp.types import PromptMessage, TextContent

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                "Mixed types string response", usage=default_usage
            )
        )
        messages = [
            "String message",
            UserMessage(content="MessageParamT response"),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        response_text = await mock_llm.generate_str(messages)
        assert response_text == "Mixed types string response"

    # Test: Generate Structured with Mixed Message Types
    @pytest.mark.asyncio
    async def test_generate_structured_with_mixed_message_types(
        self, mock_llm, default_usage
    ):
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
            UserMessage(content="MessageParamT response"),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response(
                '{"name": "MixedTypes", "value": 123}', usage=default_usage
            )
        )
        result = await mock_llm.generate_structured(messages, TestResponseModel)
        assert isinstance(result, TestResponseModel)
        assert result.name == "MixedTypes"
        assert result.value == 123
