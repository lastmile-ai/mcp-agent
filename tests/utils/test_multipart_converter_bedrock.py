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
from mcp_agent.workflows.llm.multipart_converter_bedrock import BedrockConverter


class TestBedrockConverter:
    def test_is_supported_image_type_supported(self):
        assert BedrockConverter._is_supported_image_type("image/jpeg") is True
        assert BedrockConverter._is_supported_image_type("image/png") is True

    def test_is_supported_image_type_unsupported(self):
        assert BedrockConverter._is_supported_image_type("image/gif") is False
        assert BedrockConverter._is_supported_image_type("image/webp") is False
        assert BedrockConverter._is_supported_image_type("image/svg+xml") is False
        assert BedrockConverter._is_supported_image_type("image/bmp") is False
        assert BedrockConverter._is_supported_image_type("text/plain") is False

    def test_convert_to_bedrock_empty_content(self):
        multipart = PromptMessageMultipart(role="user", content=[])
        result = BedrockConverter.convert_to_bedrock(multipart)

        assert result["role"] == "user"
        assert result["content"] == []

    def test_convert_to_bedrock_text_content(self):
        content = [TextContent(type="text", text="Hello, world!")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = BedrockConverter.convert_to_bedrock(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Hello, world!"

    def test_convert_to_bedrock_image_content_supported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/png")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = BedrockConverter.convert_to_bedrock(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert "image" in result["content"][0]
        assert result["content"][0]["image"]["format"] == "image/png"
        assert result["content"][0]["image"]["source"] == "base64data"

    def test_convert_to_bedrock_image_content_unsupported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/gif")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = BedrockConverter.convert_to_bedrock(multipart)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert "text" in result["content"][0]
        assert "unsupported format 'image/gif'" in result["content"][0]["text"]

    def test_convert_prompt_message_to_bedrock(self):
        message = PromptMessage(
            role="user", content=TextContent(type="text", text="Hello")
        )
        result = BedrockConverter.convert_prompt_message_to_bedrock(message)

        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Hello"

    def test_convert_embedded_resource_text(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert result["text"] == "Hello, world!"

    def test_convert_embedded_resource_pdf_with_blob(self):
        resource = BlobResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", blob="pdfdata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "document" in result
        assert result["document"]["format"] == "pdf"
        assert (
            result["document"]["name"] == ""
        )  # URI gets trailing slash, resulting in empty title
        assert result["document"]["source"]["bytes"] == "pdfdata"

    def test_convert_embedded_resource_pdf_without_blob(self):
        resource = TextResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", text=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "[PDF resource missing data:" in result["text"]

    def test_convert_embedded_resource_svg(self):
        resource = TextResourceContents(
            uri="file://image.svg", mimeType="image/svg+xml", text="<svg>...</svg>"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "```xml" in result["text"]
        assert "<svg>...</svg>" in result["text"]

    def test_convert_embedded_resource_image_supported(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "image" in result
        assert result["image"]["format"] == "image/png"
        assert result["image"]["source"]["bytes"] == "imagedata"

    def test_convert_embedded_resource_image_unsupported(self):
        resource = BlobResourceContents(
            uri="file://image.gif", mimeType="image/gif", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "unsupported format 'image/gif'" in result["text"]

    def test_convert_embedded_resource_image_missing_data(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "Image missing data" in result["text"]

    def test_convert_embedded_resource_text_missing_content(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "[Text content could not be extracted from" in result["text"]

    def test_convert_embedded_resource_binary_fallback(self):
        resource = BlobResourceContents(
            uri="file://data.bin",
            mimeType="application/octet-stream",
            blob="binarydata",
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = BedrockConverter._convert_embedded_resource(embedded)

        assert "text" in result
        assert "Embedded Resource" in result["text"]
        assert "unsupported format application/octet-stream" in result["text"]
        assert "10 characters" in result["text"]  # Length of "binarydata"

    def test_determine_mime_type_from_resource_attribute(self):
        resource = Mock()
        resource.mimeType = "text/plain"

        result = BedrockConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_determine_mime_type_from_uri(self):
        resource = Mock()
        resource.mimeType = None
        mock_uri = AnyUrl(url="file://test.json")
        resource.uri = mock_uri

        result = BedrockConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_blob_fallback(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = None
        resource.blob = "data"

        result = BedrockConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_default_fallback(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        resource.mimeType = None
        resource.uri = None
        # No blob attribute

        result = BedrockConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_convert_svg_resource_with_text(self):
        resource = Mock()
        resource.text = "<svg>test</svg>"

        result = BedrockConverter._convert_svg_resource(resource)

        assert "text" in result
        assert "```xml" in result["text"]
        assert "<svg>test</svg>" in result["text"]

    def test_convert_svg_resource_without_text(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        # No text attribute

        result = BedrockConverter._convert_svg_resource(resource)

        assert "text" in result
        assert result["text"] == "[SVG content could not be extracted]"

    def test_create_fallback_text_without_uri(self):
        content = TextContent(type="text", text="test")

        result = BedrockConverter._create_fallback_text("Test message", content)

        assert "text" in result
        assert result["text"] == "[Test message]"

    def test_create_fallback_text_with_uri(self):
        uri = "http://example.com/test"
        resource_content = TextResourceContents(
            uri=AnyUrl(uri), mimeType="text/plain", text="test"
        )
        embedded = EmbeddedResource(type="resource", resource=resource_content)

        result = BedrockConverter._create_fallback_text("Test message", embedded)

        assert "text" in result
        assert result["text"] == "[Test message: http://example.com/test]"

    def test_convert_tool_result_to_bedrock(self):
        content = [TextContent(type="text", text="Tool result")]
        tool_result = CallToolResult(content=content, isError=False)

        result = BedrockConverter.convert_tool_result_to_bedrock(
            tool_result, "tool_use_123"
        )

        assert "toolResult" in result
        assert result["toolResult"]["toolUseId"] == "tool_use_123"
        assert result["toolResult"]["status"] == "success"
        assert len(result["toolResult"]["content"]) == 1
        assert result["toolResult"]["content"][0]["text"] == "Tool result"

    def test_convert_tool_result_to_bedrock_error(self):
        content = [TextContent(type="text", text="Error occurred")]
        tool_result = CallToolResult(content=content, isError=True)

        result = BedrockConverter.convert_tool_result_to_bedrock(
            tool_result, "tool_use_123"
        )

        assert "toolResult" in result
        assert result["toolResult"]["toolUseId"] == "tool_use_123"
        assert result["toolResult"]["status"] == "error"
        assert len(result["toolResult"]["content"]) == 1
        assert result["toolResult"]["content"][0]["text"] == "Error occurred"

    def test_convert_tool_result_to_bedrock_empty_content(self):
        tool_result = CallToolResult(content=[], isError=False)

        result = BedrockConverter.convert_tool_result_to_bedrock(
            tool_result, "tool_use_123"
        )

        assert "toolResult" in result
        assert result["toolResult"]["toolUseId"] == "tool_use_123"
        assert result["toolResult"]["status"] == "success"
        assert len(result["toolResult"]["content"]) == 1
        assert (
            result["toolResult"]["content"][0]["text"] == "[No content in tool result]"
        )

    def test_create_tool_results_message(self):
        content = [TextContent(type="text", text="Result 1")]
        result1 = CallToolResult(content=content, isError=False)

        content2 = [TextContent(type="text", text="Result 2")]
        result2 = CallToolResult(content=content2, isError=True)

        tool_results = [("tool_1", result1), ("tool_2", result2)]

        message = BedrockConverter.create_tool_results_message(tool_results)

        assert message["role"] == "user"
        assert len(message["content"]) == 2

        # First tool result
        assert "toolResult" in message["content"][0]
        assert message["content"][0]["toolResult"]["toolUseId"] == "tool_1"
        assert message["content"][0]["toolResult"]["status"] == "success"

        # Second tool result
        assert "toolResult" in message["content"][1]
        assert message["content"][1]["toolResult"]["toolUseId"] == "tool_2"
        assert message["content"][1]["toolResult"]["status"] == "error"

    def test_convert_tool_result_with_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Resource content"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        content = [embedded]
        tool_result = CallToolResult(content=content, isError=False)

        result = BedrockConverter.convert_tool_result_to_bedrock(
            tool_result, "tool_use_123"
        )

        assert "toolResult" in result
        assert result["toolResult"]["toolUseId"] == "tool_use_123"
        assert result["toolResult"]["status"] == "success"
        assert len(result["toolResult"]["content"]) == 1
        assert result["toolResult"]["content"][0]["text"] == "Resource content"

    def test_convert_tool_result_with_image_content(self):
        content = [
            TextContent(type="text", text="Text content"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        tool_result = CallToolResult(content=content, isError=False)

        result = BedrockConverter.convert_tool_result_to_bedrock(
            tool_result, "tool_use_123"
        )

        assert "toolResult" in result
        assert result["toolResult"]["toolUseId"] == "tool_use_123"
        assert result["toolResult"]["status"] == "success"
        assert len(result["toolResult"]["content"]) == 2
        assert result["toolResult"]["content"][0]["text"] == "Text content"
        assert "image" in result["toolResult"]["content"][1]
        assert result["toolResult"]["content"][1]["image"]["format"] == "image/png"
