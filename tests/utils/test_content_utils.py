from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)

from mcp_agent.utils.content_utils import (
    get_image_data,
    get_resource_uri,
    get_text,
    is_image_content,
    is_resource_content,
    is_text_content,
)


class TestGetText:
    def test_get_text_from_text_content(self):
        content = TextContent(type="text", text="Hello, world!")
        assert get_text(content) == "Hello, world!"

    def test_get_text_from_text_resource_contents(self):
        content = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Resource text"
        )
        assert get_text(content) == "Resource text"

    def test_get_text_from_embedded_resource_with_text(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Embedded text"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert get_text(embedded) == "Embedded text"

    def test_get_text_from_embedded_resource_with_blob(self):
        resource = BlobResourceContents(
            uri="file://test.bin",
            mimeType="application/octet-stream",
            blob="binary_data",
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert get_text(embedded) is None

    def test_get_text_from_image_content(self):
        content = ImageContent(type="image", data="base64data", mimeType="image/png")
        assert get_text(content) is None


class TestGetImageData:
    def test_get_image_data_from_image_content(self):
        content = ImageContent(
            type="image", data="base64imagedata", mimeType="image/png"
        )
        assert get_image_data(content) == "base64imagedata"

    def test_get_image_data_from_embedded_resource_with_blob(self):
        resource = BlobResourceContents(
            uri="file://image.jpg", mimeType="image/jpeg", blob="imageblob"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert get_image_data(embedded) == "imageblob"

    def test_get_image_data_from_text_content(self):
        content = TextContent(type="text", text="Not an image")
        assert get_image_data(content) is None

    def test_get_image_data_from_embedded_resource_with_text(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Text content"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert get_image_data(embedded) is None


class TestGetResourceUri:
    def test_get_resource_uri_from_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt/", mimeType="text/plain", text="Test"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert get_resource_uri(embedded) == "file://test.txt/"

    def test_get_resource_uri_from_text_content(self):
        content = TextContent(type="text", text="Not a resource")
        assert get_resource_uri(content) is None

    def test_get_resource_uri_from_image_content(self):
        content = ImageContent(type="image", data="data", mimeType="image/png")
        assert get_resource_uri(content) is None


class TestIsTextContent:
    def test_is_text_content_with_text_content(self):
        content = TextContent(type="text", text="Hello")
        assert is_text_content(content) is True

    def test_is_text_content_with_text_resource_contents(self):
        content = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello"
        )
        assert is_text_content(content) is True

    def test_is_text_content_with_image_content(self):
        content = ImageContent(type="image", data="data", mimeType="image/png")
        assert is_text_content(content) is False

    def test_is_text_content_with_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert is_text_content(embedded) is False


class TestIsImageContent:
    def test_is_image_content_with_image_content(self):
        content = ImageContent(type="image", data="data", mimeType="image/png")
        assert is_image_content(content) is True

    def test_is_image_content_with_text_content(self):
        content = TextContent(type="text", text="Hello")
        assert is_image_content(content) is False

    def test_is_image_content_with_embedded_resource(self):
        resource = BlobResourceContents(
            uri="file://image.jpg", mimeType="image/jpeg", blob="imagedata"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert is_image_content(embedded) is False


class TestIsResourceContent:
    def test_is_resource_content_with_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Hello"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        assert is_resource_content(embedded) is True

    def test_is_resource_content_with_text_content(self):
        content = TextContent(type="text", text="Hello")
        assert is_resource_content(content) is False

    def test_is_resource_content_with_image_content(self):
        content = ImageContent(type="image", data="data", mimeType="image/png")
        assert is_resource_content(content) is False
