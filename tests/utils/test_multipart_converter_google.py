from unittest.mock import Mock, patch
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
from mcp_agent.workflows.llm.multipart_converter_google import GoogleConverter


class TestGoogleConverter:
    def test_is_supported_image_type_supported(self):
        assert GoogleConverter._is_supported_image_type("image/jpeg") is True
        assert GoogleConverter._is_supported_image_type("image/png") is True
        assert GoogleConverter._is_supported_image_type("image/gif") is True
        assert GoogleConverter._is_supported_image_type("image/webp") is True

    def test_is_supported_image_type_unsupported(self):
        assert GoogleConverter._is_supported_image_type("image/svg+xml") is False
        assert GoogleConverter._is_supported_image_type("image/bmp") is False
        assert GoogleConverter._is_supported_image_type("text/plain") is False

    def test_convert_to_google_empty_content(self):
        multipart = PromptMessageMultipart(role="user", content=[])
        result = GoogleConverter.convert_to_google(multipart)

        assert result.role == "user"
        assert result.parts == []

    def test_convert_to_google_text_content(self):
        content = [TextContent(type="text", text="Hello, world!")]
        multipart = PromptMessageMultipart(role="user", content=content)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Content.return_value = Mock(role="user", parts=[mock_part])

            GoogleConverter.convert_to_google(multipart)

            mock_types.Part.from_text.assert_called_once_with(text="Hello, world!")

    def test_convert_to_google_image_content_supported(self):
        content = [
            ImageContent(type="image", data="YmFzZTY0ZGF0YQ==", mimeType="image/png")
        ]  # base64 encoded "base64data"
        multipart = PromptMessageMultipart(role="user", content=content)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_bytes.return_value = mock_part
            mock_types.Content.return_value = Mock(role="user", parts=[mock_part])

            GoogleConverter.convert_to_google(multipart)

            # Should call from_bytes with decoded data
            mock_types.Part.from_bytes.assert_called_once_with(
                data=b"base64data",  # decoded base64
                mime_type="image/png",
            )

    def test_convert_to_google_image_content_unsupported(self):
        content = [ImageContent(type="image", data="base64data", mimeType="image/bmp")]
        multipart = PromptMessageMultipart(role="user", content=content)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Content.return_value = Mock(role="user", parts=[mock_part])

            GoogleConverter.convert_to_google(multipart)

            # Should call from_text with fallback message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "unsupported format 'image/bmp'" in kwargs["text"]

    def test_convert_to_google_image_content_missing_data(self):
        content = [ImageContent(type="image", data="", mimeType="image/png")]
        multipart = PromptMessageMultipart(role="user", content=content)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Content.return_value = Mock(role="user", parts=[mock_part])

            GoogleConverter.convert_to_google(multipart)

            # Should call from_text with fallback message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "Image missing data" in kwargs["text"]

    def test_convert_prompt_message_to_google(self):
        message = PromptMessage(
            role="user", content=TextContent(type="text", text="Hello")
        )

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Content.return_value = Mock(role="user", parts=[mock_part])

            GoogleConverter.convert_prompt_message_to_google(message)

            mock_types.Part.from_text.assert_called_once_with(text="Hello")

    def test_convert_embedded_resource_text(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello, world!"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            mock_types.Part.from_text.assert_called_once_with(text="Hello, world!")

    def test_convert_embedded_resource_text_missing_content(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with error message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "[Text content could not be extracted from" in kwargs["text"]

    def test_convert_embedded_resource_pdf_with_blob(self):
        resource = BlobResourceContents(
            uri="file://document.pdf",
            mimeType="application/pdf",
            blob="cGRmZGF0YQ==",  # base64 encoded "pdfdata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_bytes.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            mock_types.Part.from_bytes.assert_called_once_with(
                data=b"pdfdata",  # decoded base64
                mime_type="application/pdf",
            )

    def test_convert_embedded_resource_pdf_without_blob(self):
        resource = TextResourceContents(
            uri="file://document.pdf", mimeType="application/pdf", text=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with error message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "[PDF resource missing data:" in kwargs["text"]

    def test_convert_embedded_resource_svg(self):
        resource = TextResourceContents(
            uri="file://image.svg", mimeType="image/svg+xml", text="<svg>...</svg>"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with XML formatting
            args, kwargs = mock_types.Part.from_text.call_args
            assert "```xml" in kwargs["text"]
            assert "<svg>...</svg>" in kwargs["text"]

    def test_convert_embedded_resource_image_supported(self):
        resource = BlobResourceContents(
            uri="file://image.png",
            mimeType="image/png",
            blob="aW1hZ2VkYXRh",  # base64 encoded "imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_bytes.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            mock_types.Part.from_bytes.assert_called_once_with(
                data=b"imagedata",  # decoded base64
                mime_type="image/png",
            )

    def test_convert_embedded_resource_image_unsupported(self):
        resource = BlobResourceContents(
            uri="file://image.gif", mimeType="image/jif", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with fallback message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "unsupported format 'image/jif'" in kwargs["text"]

    def test_convert_embedded_resource_image_missing_data(self):
        resource = BlobResourceContents(
            uri="file://image.png", mimeType="image/png", blob=""
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with error message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "Image missing data" in kwargs["text"]

    def test_convert_embedded_resource_binary_fallback(self):
        resource = BlobResourceContents(
            uri="file://data.bin",
            mimeType="application/octet-stream",
            blob="binarydata",
        )
        embedded = EmbeddedResource(type="resource", resource=resource)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_embedded_resource(embedded)

            # Should call from_text with fallback message
            args, kwargs = mock_types.Part.from_text.call_args
            assert "Embedded Resource" in kwargs["text"]
            assert "unsupported format application/octet-stream" in kwargs["text"]

    def test_determine_mime_type_from_resource_attribute(self):
        resource = Mock()
        resource.mimeType = "text/plain"

        result = GoogleConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_determine_mime_type_from_uri(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = AnyUrl(url="resource://test.json")

        result = GoogleConverter._determine_mime_type(resource)
        assert result == "application/json"

    def test_determine_mime_type_blob_fallback(self):
        resource = Mock()
        resource.mimeType = None
        resource.uri = None
        resource.blob = "data"

        result = GoogleConverter._determine_mime_type(resource)
        assert result == "application/octet-stream"

    def test_determine_mime_type_default_fallback(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        resource.mimeType = None
        resource.uri = None
        # No blob attribute

        result = GoogleConverter._determine_mime_type(resource)
        assert result == "text/plain"

    def test_convert_svg_resource_with_text(self):
        resource = Mock()
        resource.text = "<svg>test</svg>"

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_svg_resource(resource)

            args, kwargs = mock_types.Part.from_text.call_args
            assert "```xml" in kwargs["text"]
            assert "<svg>test</svg>" in kwargs["text"]

    def test_convert_svg_resource_without_text(self):
        resource = Mock(spec=[])  # Create mock with no attributes
        # No text attribute

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._convert_svg_resource(resource)

            args, kwargs = mock_types.Part.from_text.call_args
            assert kwargs["text"] == "[SVG content could not be extracted]"

    def test_create_fallback_text_without_uri(self):
        content = TextContent(type="text", text="test")

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._create_fallback_text("Test message", content)

            args, kwargs = mock_types.Part.from_text.call_args
            assert kwargs["text"] == "[Test message]"

    def test_create_fallback_text_with_uri(self):
        uri = "http://example.com/test"
        resource_content = TextResourceContents(
            uri=AnyUrl(uri), mimeType="text/plain", text="test"
        )
        embedded = EmbeddedResource(type="resource", resource=resource_content)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part

            GoogleConverter._create_fallback_text("Test message", embedded)

            args, kwargs = mock_types.Part.from_text.call_args
            assert kwargs["text"] == "[Test message: http://example.com/test]"

    def test_convert_tool_result_to_google(self):
        content = [TextContent(type="text", text="Tool result")]
        tool_result = CallToolResult(content=content, isError=False)

        with (
            patch(
                "mcp_agent.workflows.llm.multipart_converter_google.types"
            ) as mock_types,
            patch.object(GoogleConverter, "_convert_content_items") as mock_convert,
        ):
            # Stub a fake Part whose to_json_dict() returns "result"
            fake_part = Mock()
            fake_part.to_json_dict.return_value = "result"
            mock_convert.return_value = [fake_part]

            # Make from_function_response return a sentinel value
            mock_part = mock_types.Part.from_function_response.return_value

            part = GoogleConverter.convert_tool_result_to_google(
                tool_result, "tool_use_123"
            )
            assert part == mock_part

            mock_types.Part.from_function_response.assert_called_once_with(
                name="tool_use_123",
                response={"content": ["result"]},
            )

    def test_convert_tool_result_to_google_error(self):
        content = [TextContent(type="text", text="Error occurred")]
        tool_result = CallToolResult(content=content, isError=True)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_function_response.return_value = mock_part

            GoogleConverter.convert_tool_result_to_google(tool_result, "tool_use_123")

            # Error case should have different response format
            args, kwargs = mock_types.Part.from_function_response.call_args
            assert kwargs["name"] == "tool_use_123"
            # Error response contains the content as string
            assert "TextContent" in str(kwargs["response"]["error"])

    def test_convert_tool_result_to_google_empty_content(self):
        tool_result = CallToolResult(content=[], isError=False)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_function_response.return_value = mock_part
            mock_types.Part.from_text.return_value = Mock()

            GoogleConverter.convert_tool_result_to_google(tool_result, "tool_use_123")

            # Should add fallback text and call function response
            mock_types.Part.from_text.assert_called_once_with(
                text="[No content in tool result]"
            )
            mock_types.Part.from_function_response.assert_called_once()

    def test_create_tool_results_message(self):
        content = [TextContent(type="text", text="Result 1")]
        result1 = CallToolResult(content=content, isError=False)

        content2 = [TextContent(type="text", text="Result 2")]
        result2 = CallToolResult(content=content2, isError=True)

        tool_results = [("tool_1", result1), ("tool_2", result2)]

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_function_response.return_value = mock_part
            mock_content = Mock()
            mock_types.Content.return_value = mock_content

            GoogleConverter.create_tool_results_message(tool_results)

            # Should call Content with user role and 2 parts
            mock_types.Content.assert_called_once_with(
                role="user", parts=[mock_part, mock_part]
            )

    def test_convert_tool_result_with_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Resource content"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        content = [embedded]
        tool_result = CallToolResult(content=content, isError=False)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Part.from_function_response.return_value = mock_part

            GoogleConverter.convert_tool_result_to_google(tool_result, "tool_use_123")

            # Should process embedded resource as text
            mock_types.Part.from_text.assert_called_once_with(text="Resource content")
            mock_types.Part.from_function_response.assert_called_once()

    def test_convert_tool_result_with_image_content(self):
        content = [
            TextContent(type="text", text="Text content"),
            ImageContent(
                type="image", data="aW1hZ2VkYXRh", mimeType="image/png"
            ),  # base64 encoded "imagedata"
        ]
        tool_result = CallToolResult(content=content, isError=False)

        with patch(
            "mcp_agent.workflows.llm.multipart_converter_google.types"
        ) as mock_types:
            mock_part = Mock()
            mock_types.Part.from_text.return_value = mock_part
            mock_types.Part.from_bytes.return_value = mock_part
            mock_types.Part.from_function_response.return_value = mock_part

            GoogleConverter.convert_tool_result_to_google(tool_result, "tool_use_123")

            # Should process both text and image content
            mock_types.Part.from_text.assert_called_once_with(text="Text content")
            mock_types.Part.from_bytes.assert_called_once_with(
                data=b"imagedata",  # decoded base64
                mime_type="image/png",
            )
            mock_types.Part.from_function_response.assert_called_once()
