import pytest

from mcp_agent.utils.mime_utils import (
    is_binary_content,
    is_image_mime_type,
    is_text_mime_type,
)


@pytest.mark.parametrize(
    "mime",
    [
        "Text/Plain",
        "application/json; charset=utf-8",
        "application/problem+json; charset=utf-8",
        " APPLICATION/XML ",
    ],
)
def test_text_media_type_with_case_and_parameters(mime: str) -> None:
    assert is_text_mime_type(mime)
    assert not is_binary_content(mime)


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("IMAGE/PNG", True),
        ("image/svg+xml; charset=utf-8", False),
        ("application/pdf", False),
    ],
)
def test_image_media_type_with_case_and_parameters(mime: str, expected: bool) -> None:
    assert is_image_mime_type(mime) is expected
