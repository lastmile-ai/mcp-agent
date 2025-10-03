from unittest.mock import Mock
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    PromptMessage,
    TextContent,
    TextResourceContents,
)

from mcp_agent.utils.prompt_message_multipart import PromptMessageMultipart
from mcp_agent.workflows.llm.multipart_converter_openai import OpenAIConverter


class TestOpenAIConverter:
    def test_is_supported_image_type_supported(self):
        assert OpenAIConverter._is_supported_image_type("image/jpeg") is True
        assert OpenAIConverter._is_supported_image_type("image/png") is True
        assert OpenAIConverter._is_supported_image_type("image/gif") is True
        assert OpenAIConverter._is_supported_image_type("image/webp") is True

    def test_is_supported_image_type_unsupported(self):
        assert OpenAIConverter._is_supported_image_type("image/svg+xml") is False
        assert OpenAIConverter._is_supported_image_type("text/plain") is False
        assert OpenAIConverter._is_supported_image_type(None) is False

    def test_convert_to_openai_empty_content(self):
        multipart = PromptMessageMultipart(role="user", content=[])
        result = OpenAIConverter.convert_to_openai(multipart)

        assert result["role"] == "user"
        assert result["content"] == ""

    def test_convert_to_openai_single_text_content(self):
        content = [TextContent(type="text", text="Hello, world!")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = OpenAIConverter.convert_to_openai(multipart)

        assert result["role"] == "user"
        assert result["content"] == "Hello, world!"

    def test_convert_to_openai_multiple_content_blocks(self):
        content = [
            TextContent(type="text", text="Hello"),
            ImageContent(type="image", data="base64data", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = OpenAIConverter.convert_to_openai(multipart)

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 2

        # First block should be text
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello"

        # Second block should be image
        assert result["content"][1]["type"] == "image_url"
        assert (
            "data:image/png;base64,base64data"
            in result["content"][1]["image_url"]["url"]
        )

    def test_convert_to_openai_concatenate_text_blocks(self):
        content = [
            TextContent(type="text", text="Hello"),
            TextContent(type="text", text="World"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = OpenAIConverter.convert_to_openai(
            multipart, concatenate_text_blocks=True
        )

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello World"

    def test_concatenate_text_blocks_with_non_text(self):
        blocks = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,data"}},
            {"type": "text", "text": "Goodbye"},
        ]

        result = OpenAIConverter._concatenate_text_blocks(blocks)

        assert len(result) == 3
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello World"
        assert result[1]["type"] == "image_url"
        assert result[2]["type"] == "text"
        assert result[2]["text"] == "Goodbye"

    def test_concatenate_text_blocks_empty(self):
        result = OpenAIConverter._concatenate_text_blocks([])
        assert result == []

    def test_convert_prompt_message_to_openai(self):
        message = PromptMessage(
            role="user", content=TextContent(type="text", text="Hello")
        )
        result = OpenAIConverter.convert_prompt_message_to_openai(message)

        assert result["role"] == "user"
        assert result["content"] == "Hello"

    def test_convert_image_content(self):
        content = ImageContent(
            type="image", data="base64imagedata", mimeType="image/png"
        )
        result = OpenAIConverter._convert_image_content(content)

        assert result["type"] == "image_url"
        assert result["image_url"]["url"] == "data:image/png;base64,base64imagedata"

    def test_convert_image_content_with_detail(self):
        content = ImageContent(
            type="image", data="base64imagedata", mimeType="image/png"
        )
        # Mock annotations with detail
        content.annotations = Mock()
        content.annotations.detail = "high"

        result = OpenAIConverter._convert_image_content(content)

        assert result["type"] == "image_url"
        assert result["image_url"]["detail"] == "high"

    def test_determine_mime_type_from_resource_attribute(self):
        resource = Mock()
        resource.mimeType = "text/plain"

        result = OpenAIConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_determine_mime_type_from_uri(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = "test.json"

        result = OpenAIConverter._determine_mime_type(resource)
        assert result == "application/json"

    def test_determine_mime_type_blob_fallback(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = None
        resource.blob = "data"

        result = OpenAIConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_default_fallback(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        resource.mimeType = None
        resource.uri = None
        # No blob attribute

        result = OpenAIConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_convert_embedded_resource_supported_image_url(self):
        resource = BlobResourceContents(
            uri="https://example.com/image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "image_url"
        assert result["image_url"]["url"] == "https://example.com/image.png"

    def test_convert_embedded_resource_supported_image_base64(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "image_url"
        assert result["image_url"]["url"] == "data:image/png;base64,imagedata"

    def test_convert_embedded_resource_pdf_url(self):
        resource = BlobResourceContents(
            uri="https://example.com/document.pdf",
            mimeType="application/pdf",
            blob="pdfdata",
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert (
            result["text"]
            == "[PDF URL: https://example.com/document.pdf]\nOpenAI requires PDF files to be uploaded or provided as base64 data."
        )

    def test_convert_embedded_resource_pdf_blob(self):
        resource = BlobResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", blob="pdfdata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "file"
        assert result["file"]["filename"] == "document.pdf"
        assert result["file"]["file_data"] == "data:application/pdf;base64,pdfdata"

    def test_convert_embedded_resource_svg(self):
        resource = TextResourceContents(
            uri="file://image.svg", mimeType="image/svg+xml", text="<svg>...</svg>"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert "<mcp-agent:file" in result["text"]
        assert (
            'title=""' in result["text"]
        )  # URI gets trailing slash, resulting in empty title
        assert "<svg>...</svg>" in result["text"]

    def test_convert_embedded_resource_text_file(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert "<mcp-agent:file" in result["text"]
        assert (
            'title=""' in result["text"]
        )  # URI gets trailing slash, resulting in empty title
        assert "Hello, world!" in result["text"]

    def test_convert_embedded_resource_binary_fallback(self):
        resource = BlobResourceContents(
            uri="file://data.bin",
            mimeType="application/octet-stream",
            blob="binarydata",
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = OpenAIConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert (
            "Binary resource:" in result["text"]
        )  # URI gets trailing slash, resulting in empty title

    def test_extract_text_from_content_blocks_string(self):
        result = OpenAIConverter._extract_text_from_content_blocks("Simple text")
        assert result == "Simple text"

    def test_extract_text_from_content_blocks_list(self):
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,data"}},
            {"type": "text", "text": "World"},
        ]

        result = OpenAIConverter._extract_text_from_content_blocks(content)
        assert result == "Hello World"

    def test_extract_text_from_content_blocks_empty(self):
        result = OpenAIConverter._extract_text_from_content_blocks([])
        assert result == ""

    def test_extract_text_from_content_blocks_no_text(self):
        content = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,data"}},
        ]

        result = OpenAIConverter._extract_text_from_content_blocks(content)
        assert result == "[Complex content converted to text]"

    def test_convert_tool_result_to_openai_text_only(self):
        content = [TextContent(type="text", text="Tool result")]
        tool_result = CallToolResult(content=content, isError=False)

        result = OpenAIConverter.convert_tool_result_to_openai(tool_result, "call_123")

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["content"] == "Tool result"

    def test_convert_tool_result_to_openai_empty_content(self):
        tool_result = CallToolResult(content=[], isError=False)

        result = OpenAIConverter.convert_tool_result_to_openai(tool_result, "call_123")

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["content"] == "[No content in tool result]"

    def test_convert_tool_result_to_openai_mixed_content(self):
        content = [
            TextContent(type="text", text="Text result"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        tool_result = CallToolResult(content=content, isError=False)

        result = OpenAIConverter.convert_tool_result_to_openai(tool_result, "call_123")

        # Should return tuple with tool message and additional user message
        assert isinstance(result, tuple)
        tool_message, additional_messages = result

        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_123"
        assert tool_message["content"] == "Text result"

        assert len(additional_messages) == 1
        assert additional_messages[0]["role"] == "user"
        assert additional_messages[0]["tool_call_id"] == "call_123"

    def test_convert_function_results_to_openai(self):
        content1 = [TextContent(type="text", text="Result 1")]
        result1 = CallToolResult(content=content1, isError=False)

        content2 = [TextContent(type="text", text="Result 2")]
        result2 = CallToolResult(content=content2, isError=True)

        results = [("call_1", result1), ("call_2", result2)]

        messages = OpenAIConverter.convert_function_results_to_openai(results)

        assert len(messages) == 2
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "call_1"
        assert messages[0]["content"] == "Result 1"

        assert messages[1]["role"] == "tool"
        assert messages[1]["tool_call_id"] == "call_2"
        assert messages[1]["content"] == "Result 2"

    def test_convert_function_results_to_openai_mixed_content(self):
        content = [
            TextContent(type="text", text="Text result"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        tool_result = CallToolResult(content=content, isError=False)
        results = [("call_1", tool_result)]

        messages = OpenAIConverter.convert_function_results_to_openai(results)

        # Should get tool message + additional user message
        assert len(messages) == 2
        assert messages[0]["role"] == "tool"
        assert messages[1]["role"] == "user"
