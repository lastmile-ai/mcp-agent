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
from pydantic import AnyUrl

from mcp_agent.utils.prompt_message_multipart import PromptMessageMultipart
from mcp_agent.workflows.llm.multipart_converter_anthropic import AnthropicConverter


class TestAnthropicConverter:
    def test_is_supported_image_type_supported(self):
        assert AnthropicConverter._is_supported_image_type("image/jpeg") is True
        assert AnthropicConverter._is_supported_image_type("image/png") is True
        assert AnthropicConverter._is_supported_image_type("image/gif") is True
        assert AnthropicConverter._is_supported_image_type("image/webp") is True

    def test_is_supported_image_type_unsupported(self):
        assert AnthropicConverter._is_supported_image_type("image/svg+xml") is False
        assert AnthropicConverter._is_supported_image_type("image/bmp") is False
        assert AnthropicConverter._is_supported_image_type("text/plain") is False

    def test_convert_to_anthropic_empty_content(self):
        multipart = PromptMessageMultipart(role="user", content=[])
        result = AnthropicConverter.convert_to_anthropic(multipart)

        assert result["role"] == "user"
        assert result["content"] == []

    def test_convert_to_anthropic_text_content(self):
        content = [TextContent(type="text", text="Hello, world!")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AnthropicConverter.convert_to_anthropic(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello, world!"

    def test_convert_to_anthropic_image_content_supported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/png")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AnthropicConverter.convert_to_anthropic(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "image"
        assert result["content"][0]["source"]["type"] == "base64"
        assert result["content"][0]["source"]["media_type"] == "image/png"
        assert result["content"][0]["source"]["data"] == "base64data"

    def test_convert_to_anthropic_image_content_unsupported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/bmp")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AnthropicConverter.convert_to_anthropic(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "unsupported format 'image/bmp'" in result["content"][0]["text"]

    def test_convert_to_anthropic_assistant_filters_non_text(self):
        content = [
            TextContent(type="text", text="Hello"),
            ImageContent(type="image", data="base64data", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="assistant", content=content)
        result = AnthropicConverter.convert_to_anthropic(multipart)

        assert result["role"] == "assistant"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello"

    def test_convert_prompt_message_to_anthropic(self):
        message = PromptMessage(
            role="user", content=TextContent(type="text", text="Hello")
        )
        result = AnthropicConverter.convert_prompt_message_to_anthropic(message)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello"

    def test_convert_embedded_resource_text_document_mode(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(
            embedded, document_mode=True
        )

        assert result["type"] == "document"
        assert (
            result["title"] == ""
        )  # URI gets a trailing slash, resulting in empty title
        assert result["source"]["type"] == "text"
        assert result["source"]["data"] == "Hello, world!"

    def test_convert_embedded_resource_text_non_document_mode(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(
            embedded, document_mode=False
        )

        assert result["type"] == "text"
        assert result["text"] == "Hello, world!"

    def test_convert_embedded_resource_pdf_with_blob(self):
        resource = BlobResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", blob="pdfdata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(embedded)

        assert result["type"] == "document"
        assert (
            result["title"] == ""
        )  # URI gets trailing slash, resulting in empty title
        assert result["source"]["type"] == "base64"
        assert result["source"]["data"] == "pdfdata"

    def test_convert_embedded_resource_svg(self):
        resource = TextResourceContents(
            uri="file://image.svg", mimeType="image/svg+xml", text="<svg>...</svg>"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert "```xml" in result["text"]
        assert "<svg>...</svg>" in result["text"]

    def test_convert_embedded_resource_image_supported(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(embedded)

        assert result["type"] == "image"
        assert result["source"]["type"] == "base64"
        assert result["source"]["data"] == "imagedata"

    def test_convert_embedded_resource_image_unsupported(self):
        resource = BlobResourceContents(
            uri="file://image.bmp", mimeType="image/bmp", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AnthropicConverter._convert_embedded_resource(embedded)

        assert result["type"] == "text"
        assert "unsupported format 'image/bmp'" in result["text"]

    def test_determine_mime_type_from_resource_attribute(self):
        resource = Mock()
        resource.mimeType = "text/plain"

        result = AnthropicConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_determine_mime_type_from_uri(self):
        resource = Mock()
        resource.mimeType = None
        mock_uri = AnyUrl(url="file://test.json")
        resource.uri = mock_uri

        result = AnthropicConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_blob_fallback(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = None
        resource.blob = "data"

        result = AnthropicConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_default_fallback(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        resource.mimeType = None
        resource.uri = None
        # No blob attribute

        result = AnthropicConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_convert_svg_resource_with_text(self):
        resource = Mock()
        resource.text = "<svg>test</svg>"

        result = AnthropicConverter._convert_svg_resource(resource)

        assert result["type"] == "text"
        assert "```xml" in result["text"]
        assert "<svg>test</svg>" in result["text"]

    def test_convert_svg_resource_without_text(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        # No text attribute

        result = AnthropicConverter._convert_svg_resource(resource)

        assert result["type"] == "text"
        assert result["text"] == "[SVG content could not be extracted]"

    def test_create_fallback_text_without_uri(self):
        content = TextContent(type="text", text="test")

        result = AnthropicConverter._create_fallback_text("Test message", content)

        assert result["type"] == "text"
        assert result["text"] == "[Test message]"

    def test_convert_tool_result_to_anthropic(self):
        content = [TextContent(type="text", text="Tool result")]
        tool_result = CallToolResult(content=content, isError=False)

        result = AnthropicConverter.convert_tool_result_to_anthropic(
            tool_result, "tool_use_123"
        )

        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "tool_use_123"
        assert result["is_error"] is False
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Tool result"

    def test_convert_tool_result_to_anthropic_empty_content(self):
        tool_result = CallToolResult(content=[], isError=False)

        result = AnthropicConverter.convert_tool_result_to_anthropic(
            tool_result, "tool_use_123"
        )

        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "tool_use_123"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "[No content in tool result]"

    def test_create_tool_results_message(self):
        content = [TextContent(type="text", text="Result 1")]
        result1 = CallToolResult(content=content, isError=False)

        content2 = [TextContent(type="text", text="Result 2")]
        result2 = CallToolResult(content=content2, isError=True)

        tool_results = [("tool_1", result1), ("tool_2", result2)]

        message = AnthropicConverter.create_tool_results_message(tool_results)

        assert message["role"] == "user"
        assert len(message["content"]) == 2

        # First tool result
        assert message["content"][0]["type"] == "tool_result"
        assert message["content"][0]["tool_use_id"] == "tool_1"
        assert message["content"][0]["is_error"] is False

        # Second tool result
        assert message["content"][1]["type"] == "tool_result"
        assert message["content"][1]["tool_use_id"] == "tool_2"
        assert message["content"][1]["is_error"] is True
