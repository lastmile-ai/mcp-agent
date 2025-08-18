from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from mcp.types import TextContent, SamplingMessage, ImageContent

from mcp_agent.config import GoogleSettings
from mcp_agent.workflows.llm.augmented_llm_google import (
    GoogleAugmentedLLM,
    RequestParams,
    GoogleMCPTypeConverter,
    mcp_content_to_google_parts,
    google_parts_to_mcp_content,
    transform_mcp_tool_schema,
)


class TestGoogleAugmentedLLM:
    """
    Tests for the GoogleAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock Google LLM instance with common mocks set up.
        """
        # Setup Google-specific context attributes using a real GoogleSettings instance
        mock_context.config.google = GoogleSettings(
            api_key="test_api_key", default_model="gemini-2.0-flash"
        )

        # Create LLM instance
        llm = GoogleAugmentedLLM(name="test", context=mock_context)

        # Apply common mocks
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="gemini-2.0-flash")
        llm._log_chat_progress = MagicMock()
        llm._log_chat_finished = MagicMock()

        # Mock the Google client
        llm.google_client = MagicMock()
        llm.google_client.models = MagicMock()
        llm.google_client.models.generate_content = AsyncMock()

        return llm

    @staticmethod
    def create_text_response(text, finish_reason="STOP", usage=None):
        """
        Creates a text response for testing in Google's format.
        """
        from google.genai import types

        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model", parts=[types.Part.from_text(text=text)]
                    ),
                    finish_reason=finish_reason,
                    safety_ratings=[],
                    citation_metadata=None,
                )
            ],
            prompt_feedback=None,
            usage_metadata=usage
            or {
                "prompt_token_count": 150,
                "candidates_token_count": 100,
                "total_token_count": 250,
            },
        )

    @staticmethod
    def create_tool_use_response(
        tool_name, tool_args, tool_id, finish_reason="STOP", usage=None
    ):
        """
        Creates a tool use response for testing in Google's format.
        """
        from google.genai import types

        function_call = types.FunctionCall(name=tool_name, args=tool_args, id=tool_id)

        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model", parts=[types.Part(function_call=function_call)]
                    ),
                    finish_reason=finish_reason,
                    safety_ratings=[],
                    citation_metadata=None,
                )
            ],
            prompt_feedback=None,
            usage_metadata=usage
            or {
                "prompt_token_count": 150,
                "candidates_token_count": 100,
                "total_token_count": 250,
            },
        )

    @staticmethod
    def create_tool_result_message(tool_result, tool_name, status="success"):
        """
        Creates a tool result message for testing in Google's format.
        """
        from google.genai import types

        if status == "success":
            function_response = {"result": tool_result}
        else:
            function_response = {"error": tool_result}

        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=tool_name, response=function_response
                )
            ],
        )

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
        assert responses[0].parts[0].text == "This is a test response"
        assert mock_llm.executor.execute.call_count == 1

        # Check the first call arguments passed to execute
        first_call_args = mock_llm.executor.execute.call_args[0][1]
        assert first_call_args.payload["model"] == "gemini-2.0-flash"
        assert first_call_args.payload["contents"][0].role == "user"
        assert first_call_args.payload["contents"][0].parts[0].text == "Test query"

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
    async def test_generate_structured(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests structured output generation using Instructor.
        """

        # Define a simple response model
        class TestResponseModel(BaseModel):
            name: str
            value: int

        # Mock the generate_str method
        mock_llm.generate_str = AsyncMock(return_value="name: Test, value: 42")

        # Mock instructor from_genai
        with patch("instructor.from_genai") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = TestResponseModel(
                name="Test", value=42
            )
            mock_instructor.return_value = mock_client

            # Patch executor.execute to be an async mock returning the expected value
            mock_llm.executor.execute = AsyncMock(
                return_value=TestResponseModel(name="Test", value=42)
            )

            # Call the method
            result = await mock_llm.generate_structured("Test query", TestResponseModel)

            # Assertions
            assert isinstance(result, TestResponseModel)
            assert result.name == "Test"
            assert result.value == 42

    # Test 4: With History
    @pytest.mark.asyncio
    async def test_with_history(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests generation with message history.
        """
        from google.genai import types

        # Setup history
        history_message = types.Content(
            role="user", parts=[types.Part.from_text(text="Previous message")]
        )
        mock_llm.history.get = MagicMock(return_value=[history_message])

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Response with history")
        )

        # Patch execute_many for tool calls
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])

        # Call LLM with history enabled
        responses = await mock_llm.generate(
            "Follow-up query", RequestParams(use_history=True)
        )

        # Assertions
        assert len(responses) == 1

        # Verify history was included in the request
        first_call_args = mock_llm.executor.execute.call_args_list[0][0]
        request_obj = first_call_args[1]
        assert len(request_obj.payload["contents"]) >= 2
        assert request_obj.payload["contents"][0] == history_message
        assert request_obj.payload["contents"][1].parts[0].text == "Follow-up query"

    # Test 5: Without History
    @pytest.mark.asyncio
    async def test_without_history(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests generation without message history.
        """
        from google.genai import types

        # Mock the history method to track if it gets called
        mock_history = MagicMock(
            return_value=[
                types.Content(
                    role="user", parts=[types.Part.from_text(text="Ignored history")]
                )
            ]
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

        # Patch execute_many for tool calls
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])

        # Check arguments passed to execute
        call_args = mock_llm.executor.execute.call_args[0]
        request_obj = call_args[1]

        # Verify history not used
        assert (
            len(
                [
                    content
                    for content in request_obj.payload["contents"]
                    if content.parts[0].text == "Ignored history"
                ]
            )
            == 0
        )

    # Test 6: Tool Usage
    @pytest.mark.asyncio
    async def test_tool_usage(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests tool usage in the LLM.
        """
        # Mock list_tools
        mock_tool_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query for the tool"}
            },
            "required": ["query"],
        }
        mock_tool_declaration = MagicMock()
        mock_tool_declaration.name = "test_tool"
        mock_tool_declaration.description = "A tool that executes a test query."
        mock_tool_declaration.inputSchema = mock_tool_schema

        # Create a custom side effect function for executor.execute
        call_count = 0

        async def custom_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First call: LLM generates a tool call request
            if call_count == 1:
                return self.create_tool_use_response(
                    tool_name="test_tool",
                    tool_args={"query": "test query"},
                    tool_id="tool_123",
                )
            # Second call: LLM generates final response after tool use
            elif call_count == 2:
                return self.create_text_response(
                    "Final response after tool use", finish_reason="STOP"
                )
            raise AssertionError(
                f"custom_side_effect called too many times: {call_count}"
            )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_side_effect)
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[
                    TextContent(
                        type="text", text="Tool executed successfully: Tool result"
                    )
                ],
                isError=False,
                tool_call_id="tool_123",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool")

        assert (
            len(responses) == 2
        )  # First LLM response (tool call), Second LLM response (final text)

        # Check first response (the tool call itself)
        assert responses[0].parts[0].function_call is not None
        assert responses[0].parts[0].function_call.name == "test_tool"
        assert responses[0].parts[0].function_call.args == {"query": "test query"}

        # Check second response (final text after tool execution)
        assert responses[1].parts[0].text == "Final response after tool use"

    # Test 7: Tool Error Handling
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests handling of errors from tool calls.
        """
        # Mock list_tools for completeness
        mock_tool_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        mock_tool_declaration = MagicMock()
        mock_tool_declaration.name = "test_tool"
        mock_tool_declaration.description = "A test tool."
        mock_tool_declaration.inputSchema = mock_tool_schema

        # Create a custom side effect function for executor.execute
        executor_call_count = 0

        async def custom_executor_side_effect(*args, **kwargs):
            nonlocal executor_call_count
            executor_call_count += 1

            # First call: LLM generates a tool call request
            if executor_call_count == 1:
                return self.create_tool_use_response(
                    tool_name="test_tool",
                    tool_args={"query": "test query"},
                    tool_id="tool_error_123",
                )
            # Second call: LLM generates final response after tool error
            elif executor_call_count == 2:
                return self.create_text_response(
                    "Response after tool error", finish_reason="STOP"
                )
            raise AssertionError(
                f"custom_executor_side_effect called too many times: {executor_call_count}"
            )

        # Setup mocks
        mock_llm.executor.execute = AsyncMock(side_effect=custom_executor_side_effect)
        mock_llm.executor.execute_many = AsyncMock(return_value=[None])
        mock_llm.call_tool = AsyncMock(
            return_value=MagicMock(
                content=[
                    TextContent(type="text", text="Tool execution failed with error")
                ],
                isError=True,
                tool_call_id="tool_error_123",
            )
        )

        # Call LLM
        responses = await mock_llm.generate("Test query with tool error")

        # Assertions
        assert len(responses) == 2  # First response is tool call, second is final text

        # Check first response (the tool call itself from the LLM)
        assert responses[0].parts[0].function_call is not None
        assert responses[0].parts[0].function_call.name == "test_tool"
        assert responses[0].parts[0].function_call.args == {"query": "test query"}

        # Check second response (final text after tool error)
        assert responses[1].parts[0].text == "Response after tool error"

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
        mock_llm.select_model = AsyncMock(return_value="gemini-2.0-pro")

        # Setup mock executor
        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Model selection test")
        )

        # Call LLM with a specific model in request_params
        request_params = RequestParams(model="gemini-1.5-flash")
        await mock_llm.generate("Test query", request_params)

        # Assertions
        assert mock_llm.select_model.call_count == 1
        # Verify the model parameter was passed (check the model name in request_params)
        assert mock_llm.select_model.call_args[0][0].model == "gemini-1.5-flash"

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
        Tests the GoogleMCPTypeConverter for converting between Google and MCP types.
        """
        from google.genai import types

        # Test conversion from Google message to MCP result
        google_message = types.Content(
            role="model", parts=[types.Part.from_text(text="Test content")]
        )

        mcp_result = GoogleMCPTypeConverter.to_mcp_message_result(google_message)
        assert mcp_result.role == "assistant"
        assert mcp_result.content.text == "Test content"

        # Test conversion from MCP message param to Google message
        mcp_message = SamplingMessage(
            role="user", content=TextContent(type="text", text="Test MCP content")
        )
        google_param = GoogleMCPTypeConverter.from_mcp_message_param(mcp_message)
        assert google_param.role == "user"
        assert len(google_param.parts) == 1
        assert google_param.parts[0].text == "Test MCP content"

    # Test 12: Content Block Conversions
    def test_content_block_conversions(self):
        """
        Tests conversion between MCP content formats and Google content blocks.
        """
        # Test text content conversion
        text_content = [TextContent(type="text", text="Hello world")]
        google_parts = mcp_content_to_google_parts(text_content)
        assert len(google_parts) == 1
        assert google_parts[0].text == "Hello world"

        # Convert back to MCP
        mcp_blocks = google_parts_to_mcp_content(google_parts)
        assert len(mcp_blocks) == 1
        assert isinstance(mcp_blocks[0], TextContent)
        assert mcp_blocks[0].text == "Hello world"

        # Test image content (with base64 encoded data)
        import base64

        test_image_data = base64.b64encode(b"fake image data").decode("utf-8")

        image_content = [
            ImageContent(type="image", data=test_image_data, mimeType="image/png")
        ]
        google_parts = mcp_content_to_google_parts(image_content)
        assert len(google_parts) == 1
        assert (
            google_parts[0].file_data is None
        )  # Because we can't directly test the binary data

    # Test 13: Tool Schema Transformation
    def test_transform_mcp_tool_schema(self):
        """
        Tests the transformation of MCP tool schema to Google compatible schema.
        """
        # Test basic property conversion
        basic_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name"},
                "age": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        }

        transformed = transform_mcp_tool_schema(basic_schema)

        assert transformed["type"] == "object"
        assert "name" in transformed["properties"]
        assert transformed["properties"]["name"]["type"] == "string"
        assert "age" in transformed["properties"]
        assert transformed["properties"]["age"]["type"] == "integer"
        assert transformed["properties"]["age"]["minimum"] == 0
        assert "required" in transformed

        # Test camelCase to snake_case conversion
        camel_case_schema = {
            "type": "object",
            "properties": {
                "longText": {"type": "string", "maxLength": 100},
            },
        }

        transformed = transform_mcp_tool_schema(camel_case_schema)

        assert "max_length" in transformed["properties"]["longText"]
        assert transformed["properties"]["longText"]["max_length"] == 100

        # Test nested schema conversion
        nested_schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "firstName": {"type": "string"},
                        "lastName": {"type": "string"},
                    },
                }
            },
        }

        transformed = transform_mcp_tool_schema(nested_schema)

        assert "user" in transformed["properties"]
        assert transformed["properties"]["user"]["type"] == "object"
        assert "firstName" in transformed["properties"]["user"]["properties"]
        assert "lastName" in transformed["properties"]["user"]["properties"]

        # Test anyOf handling (nullable types)
        nullable_schema = {
            "type": "object",
            "properties": {
                "optionalField": {"anyOf": [{"type": "string"}, {"type": "null"}]}
            },
        }

        transformed = transform_mcp_tool_schema(nullable_schema)

        assert "optionalField" in transformed["properties"]
        assert transformed["properties"]["optionalField"]["type"] == "string"
        assert transformed["properties"]["optionalField"]["nullable"] is True

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
        assert responses[0].parts[0].text == "String input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["contents"][0].role == "user"
        assert (
            req.payload["contents"][0].parts[0].text
            == "This is a simple string message"
        )

    # Test: Generate with MessageParamT Input
    @pytest.mark.asyncio
    async def test_generate_with_message_param_input(self, mock_llm):
        """
        Tests generate() method with MessageParamT input (Google Content).
        """
        from google.genai import types

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("MessageParamT input response")
        )
        # Create MessageParamT (Google Content)
        message_param = types.Content(
            role="user",
            parts=[types.Part.from_text(text="This is a MessageParamT message")],
        )
        responses = await mock_llm.generate(message_param)
        assert len(responses) == 1
        assert responses[0].parts[0].text == "MessageParamT input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["contents"][0].role == "user"
        assert (
            req.payload["contents"][0].parts[0].text
            == "This is a MessageParamT message"
        )

    # Test: Generate with PromptMessage Input
    @pytest.mark.asyncio
    async def test_generate_with_prompt_message_input(self, mock_llm):
        """
        Tests generate() method with PromptMessage input (MCP PromptMessage).
        """
        from mcp.types import PromptMessage, TextContent

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("PromptMessage input response")
        )
        prompt_message = PromptMessage(
            role="user",
            content=TextContent(type="text", text="This is a PromptMessage"),
        )
        responses = await mock_llm.generate(prompt_message)
        assert len(responses) == 1
        assert responses[0].parts[0].text == "PromptMessage input response"
        req = mock_llm.executor.execute.call_args[0][1]
        assert req.payload["contents"][0].role == "user"
        assert req.payload["contents"][0].parts[0].text == "This is a PromptMessage"

    # Test: Generate with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_with_mixed_message_types(self, mock_llm):
        """
        Tests generate() method with a list containing mixed message types.
        """
        from mcp.types import PromptMessage, TextContent
        from google.genai import types

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Mixed message types response")
        )
        messages = [
            "String message",
            types.Content(
                role="user", parts=[types.Part.from_text(text="MessageParamT response")]
            ),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
        responses = await mock_llm.generate(messages)
        assert len(responses) == 1
        assert responses[0].parts[0].text == "Mixed message types response"

    # Test: Generate String with Mixed Message Types List
    @pytest.mark.asyncio
    async def test_generate_str_with_mixed_message_types(self, mock_llm):
        """
        Tests generate_str() method with mixed message types.
        """
        from mcp.types import PromptMessage, TextContent
        from google.genai import types

        mock_llm.executor.execute = AsyncMock(
            return_value=self.create_text_response("Mixed types string response")
        )
        messages = [
            "String message",
            types.Content(
                role="user", parts=[types.Part.from_text(text="MessageParamT response")]
            ),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]
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
        from google.genai import types

        class TestResponseModel(BaseModel):
            name: str
            value: int

        messages = [
            "String message",
            types.Content(
                role="user", parts=[types.Part.from_text(text="MessageParamT response")]
            ),
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="PromptMessage content"),
            ),
        ]

        # Mock the generate_str method
        mock_llm.generate_str = AsyncMock(return_value="name: MixedTypes, value: 123")

        # Patch instructor.from_genai to return the expected model
        with patch("instructor.from_genai") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = TestResponseModel(
                name="MixedTypes", value=123
            )
            mock_instructor.return_value = mock_client

            # Patch executor.execute to be an async mock returning the expected value
            mock_llm.executor.execute = AsyncMock(
                return_value=TestResponseModel(name="MixedTypes", value=123)
            )

            result = await mock_llm.generate_structured(messages, TestResponseModel)
            assert isinstance(result, TestResponseModel)
            assert result.name == "MixedTypes"
            assert result.value == 123

    @pytest.mark.asyncio
    async def test_parallel_tool_calls(self, mock_llm: GoogleAugmentedLLM):
        """
        Tests that parallel tool calls return a single Content with multiple function response parts.
        """
        from google.genai import types

        parallel_tool_response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="tool1", args={"param": "value1"}, id="call_1"
                                )
                            ),
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="tool2", args={"param": "value2"}, id="call_2"
                                )
                            ),
                        ],
                    ),
                    finish_reason="STOP",
                )
            ]
        )

        final_response = self.create_text_response(
            "Final response after parallel tools"
        )

        mock_llm.executor.execute = AsyncMock(
            side_effect=[parallel_tool_response, final_response]
        )

        async def mock_execute_tool_call(function_call):
            if function_call.name == "tool1":
                return types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name="tool1", response={"result": "Result from tool 1"}
                        )
                    ],
                )
            elif function_call.name == "tool2":
                return types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name="tool2", response={"result": "Result from tool 2"}
                        )
                    ],
                )

        mock_llm.execute_tool_call = AsyncMock(side_effect=mock_execute_tool_call)

        mock_llm.executor.execute_many = AsyncMock(
            return_value=[
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name="tool1", response={"result": "Result from tool 1"}
                        )
                    ],
                ),
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name="tool2", response={"result": "Result from tool 2"}
                        )
                    ],
                ),
            ]
        )

        # Track the messages to verify our fix combines tool responses correctly
        original_messages = []

        def track_messages(messages):
            original_messages.extend(messages)
            return messages

        mock_llm.history.set = MagicMock(side_effect=track_messages)

        responses = await mock_llm.generate("Test parallel tool calls")

        # Verify the responses
        assert len(responses) == 2  # Tool call response + final response
        assert len(responses[0].parts) == 2  # Two parallel tool calls
        assert responses[0].parts[0].function_call.name == "tool1"
        assert responses[0].parts[1].function_call.name == "tool2"
        assert responses[1].parts[0].text == "Final response after parallel tools"

        # Verify that only ONE tool response message was added to messages
        tool_messages = [
            msg
            for msg in original_messages
            if hasattr(msg, "role") and msg.role == "tool"
        ]
        assert len(tool_messages) == 1, (
            f"Expected 1 tool message, got {len(tool_messages)}"
        )

        # Verify the single tool message contains both function responses
        tool_message = tool_messages[0]
        assert len(tool_message.parts) == 2, (
            f"Expected 2 parts in tool message, got {len(tool_message.parts)}"
        )

        # Verify both tool responses are present in the combined message
        part_names = [
            part.function_response.name
            for part in tool_message.parts
            if part.function_response
        ]
        assert "tool1" in part_names, "tool1 response not found in combined message"
        assert "tool2" in part_names, "tool2 response not found in combined message"
