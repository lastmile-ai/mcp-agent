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
from mcp_agent.workflows.llm.multipart_converter_azure import AzureConverter


class TestAzureConverter:
    def test_is_supported_image_type_supported(self):
        assert AzureConverter._is_supported_image_type("image/jpeg") is True
        assert AzureConverter._is_supported_image_type("image/png") is True
        assert AzureConverter._is_supported_image_type("image/gif") is True
        assert AzureConverter._is_supported_image_type("image/webp") is True

    def test_is_supported_image_type_unsupported(self):
        assert AzureConverter._is_supported_image_type("image/svg+xml") is False
        assert AzureConverter._is_supported_image_type("image/bmp") is False
        assert AzureConverter._is_supported_image_type("text/plain") is False

    def test_convert_to_azure_empty_content(self):
        multipart = PromptMessageMultipart(role="user", content=[])
        result = AzureConverter.convert_to_azure(multipart)

        assert result.role == "user"
        assert result.content == ""

    def test_convert_to_azure_text_content(self):
        content = [TextContent(type="text", text="Hello, world!")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AzureConverter.convert_to_azure(multipart)

        assert result.role == "user"
        assert isinstance(result.content, list)
        assert "Hello, world!" in result.content[0].text

    def test_convert_to_azure_image_content_supported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/png")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AzureConverter.convert_to_azure(multipart)

        assert result.role == "user"
        assert isinstance(result.content, list)
        assert "data:image/png;base64,base64data" in result.content[0].image_url.url

    def test_convert_to_azure_image_content_unsupported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/bmp")]
        multipart = PromptMessageMultipart(role="user", content=content)
        result = AzureConverter.convert_to_azure(multipart)

        assert result.role == "user"
        assert isinstance(result.content, list)
        assert "unsupported format 'image/bmp'" in result.content[0].text

    def test_convert_to_azure_assistant_filters_non_text(self):
        content = [
            TextContent(type="text", text="Hello"),
            ImageContent(type="image", data="base64data", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="assistant", content=content)
        result = AzureConverter.convert_to_azure(multipart)

        assert result.role == "assistant"
        assert result.content == "Hello"

    def test_convert_prompt_message_to_azure(self):
        message = PromptMessage(
            role="user", content=TextContent(type="text", text="Hello")
        )
        result = AzureConverter.convert_prompt_message_to_azure(message)

        assert result.role == "user"
        assert isinstance(result.content, list)
        assert "Hello" in result.content[0].text

    def test_convert_embedded_resource_text(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "text")
        assert result.text == "Hello, world!"

    def test_convert_embedded_resource_pdf(self):
        resource = BlobResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", blob="pdfdata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "text")
        assert "[PDF resource:" in result.text

    def test_convert_embedded_resource_svg(self):
        resource = TextResourceContents(
            uri="file://image.svg", mimeType="image/svg+xml", text="<svg>...</svg>"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "text")
        assert "```xml" in result.text
        assert "<svg>...</svg>" in result.text

    def test_convert_embedded_resource_image_supported_with_url(self):
        resource = BlobResourceContents(
            uri="https://example.com/image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "image_url")
        assert result.image_url.url == "https://example.com/image.png"

    def test_convert_embedded_resource_image_supported_with_blob(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "image_url")
        assert "data:image/png;base64,imagedata" in result.image_url.url

    def test_convert_embedded_resource_image_unsupported(self):
        resource = BlobResourceContents(
            uri="file://image.bmp", mimeType="image/bmp", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "text")
        assert "unsupported format 'image/bmp'" in result.text

    def test_convert_embedded_resource_image_missing_data(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        result = AzureConverter._convert_embedded_resource(embedded)

        assert hasattr(result, "text")
        assert "Image missing data" in result.text

    def test_determine_mime_type_from_resource_attribute(self):
        resource = Mock()
        resource.mimeType = "text/plain"

        result = AzureConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_determine_mime_type_from_uri(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = AnyUrl(url="resource://test.json")

        result = AzureConverter._determine_mime_type(resource)
        assert result == "application/json"

    def test_determine_mime_type_blob_fallback(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = None
        resource.blob = "data"

        result = AzureConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_default_fallback(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        resource.mimeType = None
        resource.uri = None
        # No blob attribute

        result = AzureConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_convert_svg_resource_with_text(self):
        resource = Mock()
        resource.text = "<svg>test</svg>"

        result = AzureConverter._convert_svg_resource(resource)

        assert hasattr(result, "text")
        assert "```xml" in result.text
        assert "<svg>test</svg>" in result.text

    def test_convert_svg_resource_without_text(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        # No text attribute

        result = AzureConverter._convert_svg_resource(resource)

        assert hasattr(result, "text")
        assert result.text == "[SVG content could not be extracted]"

    def test_create_fallback_text_without_uri(self):
        content = TextContent(type="text", text="test")

        result = AzureConverter._create_fallback_text("Test message", content)

        assert hasattr(result, "text")
        assert result.text == "[Test message]"

    def test_create_fallback_text_with_uri(self):
        uri = "http://example.com/test"
        resource_content = TextResourceContents(
            uri=AnyUrl(uri), mimeType="text/plain", text="test"
        )
        embedded = EmbeddedResource(type="resource", resource=resource_content)

        result = AzureConverter._create_fallback_text("Test message", embedded)

        assert hasattr(result, "text")
        assert result.text == "[Test message: http://example.com/test]"

    def test_convert_tool_result_to_azure(self):
        content = [TextContent(type="text", text="Tool result")]
        tool_result = CallToolResult(content=content, isError=False)

        result = AzureConverter.convert_tool_result_to_azure(
            tool_result, "tool_use_123"
        )

        assert result.role == "tool"
        assert isinstance(result.content, str)
        assert "Tool result" in result.content

    def test_convert_tool_result_to_azure_empty_content(self):
        tool_result = CallToolResult(content=[], isError=False)

        result = AzureConverter.convert_tool_result_to_azure(
            tool_result, "tool_use_123"
        )

        assert result.role == "tool"
        assert isinstance(result.content, str)
        assert "[No content in tool result]" in result.content

    def test_create_tool_results_message(self):
        content = [TextContent(type="text", text="Result 1")]
        result1 = CallToolResult(content=content, isError=False)

        content2 = [TextContent(type="text", text="Result 2")]
        result2 = CallToolResult(content=content2, isError=True)

        tool_results = [("tool_1", result1), ("tool_2", result2)]

        messages = AzureConverter.create_tool_results_message(tool_results)

        assert isinstance(messages, list)
        assert len(messages) == 2

        assert messages[0].tool_call_id == "tool_1"
        assert "Result 1" in messages[0].content

        assert messages[1].tool_call_id == "tool_2"
        assert "Result 2" in messages[1].content

    def test_convert_tool_result_with_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Resource content"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        content = [embedded]
        tool_result = CallToolResult(content=content, isError=False)

        result = AzureConverter.convert_tool_result_to_azure(
            tool_result, "tool_use_123"
        )

        assert result.role == "tool"
        assert isinstance(result.content, str)
        assert "Resource content" in result.content

    def test_convert_tool_result_with_mixed_content(self):
        content = [
            TextContent(type="text", text="Text content"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        tool_result = CallToolResult(content=content, isError=False)

        result = AzureConverter.convert_tool_result_to_azure(
            tool_result, "tool_use_123"
        )

        assert result.role == "tool"
        assert isinstance(result.content, str)
        assert "Text content" in result.content
        assert "data:image/png;base64,imagedata" in result.content
