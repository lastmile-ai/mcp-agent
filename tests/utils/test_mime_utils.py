from mcp_agent.utils.mime_utils import (
    guess_mime_type,
    is_binary_content,
    is_image_mime_type,
    is_text_mime_type,
)


class TestGuessMimeType:
    def test_guess_mime_type_python_file(self):
        assert guess_mime_type("script.py") == "text/x-python"

    def test_guess_mime_type_json_file(self):
        assert guess_mime_type("data.json") == "application/json"

    def test_guess_mime_type_txt_file(self):
        assert guess_mime_type("readme.txt") == "text/plain"

    def test_guess_mime_type_html_file(self):
        assert guess_mime_type("index.html") == "text/html"

    def test_guess_mime_type_png_file(self):
        assert guess_mime_type("image.png") == "image/png"

    def test_guess_mime_type_webp_file(self):
        assert guess_mime_type("image.webp") == "image/webp"

    def test_guess_mime_type_unknown_extension(self):
        assert guess_mime_type("file.unknown") == "application/octet-stream"

    def test_guess_mime_type_no_extension(self):
        assert guess_mime_type("filename") == "application/octet-stream"


class TestIsTextMimeType:
    def test_is_text_mime_type_text_plain(self):
        assert is_text_mime_type("text/plain") is True

    def test_is_text_mime_type_text_html(self):
        assert is_text_mime_type("text/html") is True

    def test_is_text_mime_type_application_json(self):
        assert is_text_mime_type("application/json") is True

    def test_is_text_mime_type_application_javascript(self):
        assert is_text_mime_type("application/javascript") is True

    def test_is_text_mime_type_application_xml(self):
        assert is_text_mime_type("application/xml") is True

    def test_is_text_mime_type_application_yaml(self):
        assert is_text_mime_type("application/yaml") is True

    def test_is_text_mime_type_application_toml(self):
        assert is_text_mime_type("application/toml") is True

    def test_is_text_mime_type_custom_xml(self):
        assert is_text_mime_type("application/custom+xml") is True

    def test_is_text_mime_type_custom_json(self):
        assert is_text_mime_type("application/vnd.api+json") is True

    def test_is_text_mime_type_custom_yaml(self):
        assert is_text_mime_type("application/custom+yaml") is True

    def test_is_text_mime_type_custom_text(self):
        assert is_text_mime_type("application/custom+text") is True

    def test_is_text_mime_type_image_png(self):
        assert is_text_mime_type("image/png") is False

    def test_is_text_mime_type_application_pdf(self):
        assert is_text_mime_type("application/pdf") is False

    def test_is_text_mime_type_application_octet_stream(self):
        assert is_text_mime_type("application/octet-stream") is False

    def test_is_text_mime_type_empty_string(self):
        assert is_text_mime_type("") is False

    def test_is_text_mime_type_none(self):
        assert is_text_mime_type(None) is False


class TestIsBinaryContent:
    def test_is_binary_content_image(self):
        assert is_binary_content("image/png") is True

    def test_is_binary_content_pdf(self):
        assert is_binary_content("application/pdf") is True

    def test_is_binary_content_text(self):
        assert is_binary_content("text/plain") is False

    def test_is_binary_content_json(self):
        assert is_binary_content("application/json") is False

    def test_is_binary_content_xml(self):
        assert is_binary_content("application/xml") is False


class TestIsImageMimeType:
    def test_is_image_mime_type_png(self):
        assert is_image_mime_type("image/png") is True

    def test_is_image_mime_type_jpeg(self):
        assert is_image_mime_type("image/jpeg") is True

    def test_is_image_mime_type_gif(self):
        assert is_image_mime_type("image/gif") is True

    def test_is_image_mime_type_webp(self):
        assert is_image_mime_type("image/webp") is True

    def test_is_image_mime_type_svg_xml(self):
        # SVG is excluded from being considered an image for processing purposes
        assert is_image_mime_type("image/svg+xml") is False

    def test_is_image_mime_type_text_plain(self):
        assert is_image_mime_type("text/plain") is False

    def test_is_image_mime_type_application_pdf(self):
        assert is_image_mime_type("application/pdf") is False
