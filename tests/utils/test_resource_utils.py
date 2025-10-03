import base64
import tempfile
from pathlib import Path

import pytest
from mcp.types import BlobResourceContents, EmbeddedResource, TextResourceContents
from pydantic import AnyUrl

from mcp_agent.utils.resource_utils import (
    create_blob_resource,
    create_embedded_resource,
    create_image_content,
    create_resource_reference,
    create_resource_uri,
    create_text_resource,
    extract_title_from_uri,
    find_resource_file,
    load_resource_content,
    normalize_uri,
)


class TestFindResourceFile:
    def test_find_resource_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create a prompt file
            prompt_file = tmppath / "prompt.txt"
            prompt_file.write_text("test prompt")

            # Create a resource file in same directory
            resource_file = tmppath / "resource.txt"
            resource_file.write_text("test resource")

            # Find the resource relative to the prompt file
            found = find_resource_file("resource.txt", [prompt_file])
            assert found == resource_file

    def test_find_resource_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            prompt_file = tmppath / "prompt.txt"
            prompt_file.write_text("test prompt")

            found = find_resource_file("nonexistent.txt", [prompt_file])
            assert found is None

    def test_find_resource_file_multiple_prompt_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create subdirectories
            subdir1 = tmppath / "sub1"
            subdir2 = tmppath / "sub2"
            subdir1.mkdir()
            subdir2.mkdir()

            # Create prompt files
            prompt1 = subdir1 / "prompt1.txt"
            prompt2 = subdir2 / "prompt2.txt"
            prompt1.write_text("prompt 1")
            prompt2.write_text("prompt 2")

            # Create resource in second subdirectory
            resource_file = subdir2 / "resource.txt"
            resource_file.write_text("test resource")

            # Should find resource relative to second prompt file
            found = find_resource_file("resource.txt", [prompt1, prompt2])
            assert found == resource_file


class TestLoadResourceContent:
    def test_load_resource_content_text_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            prompt_file = tmppath / "prompt.txt"
            prompt_file.write_text("test")

            resource_file = tmppath / "resource.txt"
            resource_file.write_text("Hello, world!", encoding="utf-8")

            content, mime_type, is_binary = load_resource_content(
                "resource.txt", [prompt_file]
            )

            assert content == "Hello, world!"
            assert mime_type == "text/plain"
            assert is_binary is False

    def test_load_resource_content_binary_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            prompt_file = tmppath / "prompt.txt"
            prompt_file.write_text("test")

            resource_file = tmppath / "image.png"
            binary_data = b"\x89PNG\r\n\x1a\n"  # PNG header
            resource_file.write_bytes(binary_data)

            content, mime_type, is_binary = load_resource_content(
                "image.png", [prompt_file]
            )

            expected_content = base64.b64encode(binary_data).decode("utf-8")
            assert content == expected_content
            assert mime_type == "image/png"
            assert is_binary is True

    def test_load_resource_content_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            prompt_file = tmppath / "prompt.txt"
            prompt_file.write_text("test")

            with pytest.raises(
                FileNotFoundError, match="Resource not found: nonexistent.txt"
            ):
                load_resource_content("nonexistent.txt", [prompt_file])


class TestCreateResourceUri:
    def test_create_resource_uri(self):
        result = create_resource_uri("test/path/file.txt")
        assert result == "resource://mcp-agent/file.txt"

    def test_create_resource_uri_simple_filename(self):
        result = create_resource_uri("file.txt")
        assert result == "resource://mcp-agent/file.txt"


class TestCreateResourceReference:
    def test_create_resource_reference(self):
        uri = "resource://test/file.txt"
        mime_type = "text/plain"

        result = create_resource_reference(uri, mime_type)

        assert isinstance(result, EmbeddedResource)
        assert result.type == "resource"
        assert isinstance(result.resource, TextResourceContents)
        assert str(result.resource.uri) == uri
        assert result.resource.mimeType == mime_type
        assert result.resource.text == ""


class TestCreateEmbeddedResource:
    def test_create_embedded_resource_text(self):
        result = create_embedded_resource(
            "test.txt", "Hello, world!", "text/plain", False
        )

        assert isinstance(result, EmbeddedResource)
        assert result.type == "resource"
        assert isinstance(result.resource, TextResourceContents)
        assert result.resource.uri == AnyUrl(url="resource://mcp-agent/test.txt")
        assert result.resource.mimeType == "text/plain"
        assert result.resource.text == "Hello, world!"

    def test_create_embedded_resource_binary(self):
        binary_content = base64.b64encode(b"binary data").decode("utf-8")
        result = create_embedded_resource(
            "image.png", binary_content, "image/png", True
        )

        assert isinstance(result, EmbeddedResource)
        assert result.type == "resource"
        assert isinstance(result.resource, BlobResourceContents)
        assert result.resource.uri == AnyUrl(url="resource://mcp-agent/image.png")
        assert result.resource.mimeType == "image/png"
        assert result.resource.blob == binary_content


class TestCreateImageContent:
    def test_create_image_content(self):
        data = "base64imagedata"
        mime_type = "image/png"

        result = create_image_content(data, mime_type)

        assert result.type == "image"
        assert result.data == data
        assert result.mimeType == mime_type


class TestCreateBlobResource:
    def test_create_blob_resource(self):
        content = base64.b64encode(b"binary data").decode("utf-8")
        result = create_blob_resource(
            "file://test.bin", content, "application/octet-stream"
        )

        assert isinstance(result, EmbeddedResource)
        assert result.type == "resource"
        assert isinstance(result.resource, BlobResourceContents)
        assert result.resource.uri == AnyUrl(url="file://test.bin")
        assert result.resource.mimeType == "application/octet-stream"
        assert result.resource.blob == content


class TestCreateTextResource:
    def test_create_text_resource(self):
        content = "Hello, world!"
        result = create_text_resource("file://test.txt", content, "text/plain")

        assert isinstance(result, EmbeddedResource)
        assert result.type == "resource"
        assert isinstance(result.resource, TextResourceContents)
        assert result.resource.uri == AnyUrl(url="file://test.txt")
        assert result.resource.mimeType == "text/plain"
        assert result.resource.text == content


class TestNormalizeUri:
    def test_normalize_uri_empty_string(self):
        assert normalize_uri("") == ""

    def test_normalize_uri_already_valid_uri(self):
        uri = "https://example.com/file.txt"
        assert normalize_uri(uri) == uri

    def test_normalize_uri_file_uri(self):
        uri = "file:///path/to/file.txt"
        assert normalize_uri(uri) == uri

    def test_normalize_uri_absolute_path(self):
        path = "/path/to/file.txt"
        assert normalize_uri(path) == "file:///path/to/file.txt"

    def test_normalize_uri_relative_path(self):
        path = "path/to/file.txt"
        assert normalize_uri(path) == "file:///path/to/file.txt"

    def test_normalize_uri_windows_path(self):
        path = "C:\\path\\to\\file.txt"
        assert normalize_uri(path) == "file:///C:/path/to/file.txt"

    def test_normalize_uri_simple_filename(self):
        filename = "file.txt"
        assert normalize_uri(filename) == "file:///file.txt"


class TestExtractTitleFromUri:
    def test_extract_title_from_http_uri(self):
        uri = AnyUrl(url="http://example.com/path/to/document.pdf")

        result = extract_title_from_uri(uri)
        assert result == "document.pdf"

    def test_extract_title_from_https_uri(self):
        uri = AnyUrl(url="https://example.com/files/report.txt")

        result = extract_title_from_uri(uri)
        assert result == "report.txt"

    def test_extract_title_from_file_uri(self):
        uri = AnyUrl(url="file:///local/path/document.txt")

        result = extract_title_from_uri(uri)
        assert result == "document.txt"

    def test_extract_title_from_uri_no_path(self):
        mock_uri = AnyUrl(url="https://example.com")

        result = extract_title_from_uri(mock_uri)
        assert result == "https://example.com/"

    def test_extract_title_from_uri_empty_filename(self):
        uri = AnyUrl(url="https://example.com/path/to/")

        result = extract_title_from_uri(uri)
        assert result == "to"

    def test_extract_title_from_uri_exception(self):
        mock_uri = AnyUrl(url="http://example.com/file.txt")

        result = extract_title_from_uri(mock_uri)
        assert result == "file.txt"
